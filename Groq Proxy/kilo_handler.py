"""Kilo chat turn processor — synthesis-only architecture."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable

from backend import invoke_synthesis_llm, is_backend_failure
from bridge_guards import (
    BackendEvaluation,
    classify_backend_result,
    classify_parse_failure,
    log_layer_issue,
    should_cache_response,
    validate_outbound_tool_calls,
)
from orchestrator import OrchestratorDecision, orchestrate_turn, synthesis_orchestrator_enabled
from prompt_pipeline import (
    JSON_REPAIR_SUFFIX,
    _user_turn_key,
    coerce_text_to_completion,
    detect_intent,
    synthesize_backend_failure_response,
)
from response_pipeline import parse_assistant_response, unwrap_grok_cli_stdout_auto
from synthesis_pipeline import build_synthesis_prompt, synthesis_output_to_kilo

LogFn = Callable[[str], None]
InvokeFn = Callable[..., object]


@dataclass
class ChatTurnResult:
    content: str | None = None
    tool_calls: list = field(default_factory=list)
    cache: bool = False
    error_message: str | None = None
    error_status: int = 502
    request_id: str = ""
    backend: str = ""
    total_s: float = 0.0
    decision_reason: str = ""
    action: str = ""


def _parse_backend(
    backend_result,
    allowed_tool_names: list[str],
    log: LogFn,
    request_id: str,
) -> tuple[str | None, list, BackendEvaluation | None]:
    output_fmt = os.environ.get("GROK_OUTPUT_FORMAT", "plain")
    parse_text, grok_meta = unwrap_grok_cli_stdout_auto(
        backend_result.stdout or "",
        output_fmt,
    )
    if backend_result.stderr:
        log(f"RAW_BACKEND_STDERR: {backend_result.stderr[:400]}")
    if backend_result.stdout:
        log(
            f"RAW_BACKEND_STDOUT ({backend_result.backend}, first 600): "
            f"{backend_result.stdout[:600].replace(chr(10), ' ')[:600]}"
        )

    backend_eval = classify_backend_result(
        backend_result,
        parse_text=parse_text,
        grok_meta=grok_meta,
    )
    if not backend_eval.ok or is_backend_failure(backend_result):
        log_layer_issue(log, backend_eval, request_id)
        return None, [], backend_eval

    clean_response, tool_calls = parse_assistant_response(
        parse_text or backend_result.stderr,
        allowed_tool_names=allowed_tool_names,
    )
    return clean_response, tool_calls, backend_eval


def _run_synthesis(
    messages: list,
    tools: list | None,
    decision: OrchestratorDecision,
    allowed_tool_names: list[str],
    log: LogFn,
    invoke: InvokeFn,
    request_id: str,
) -> ChatTurnResult:
    prompt = build_synthesis_prompt(
        messages,
        tools,
        kind=decision.synthesis_kind,
    )
    log(
        f"🧠 SYNTHESIS (request_id={request_id}, kind={decision.synthesis_kind}, "
        f"prompt_len={len(prompt)}): {prompt[:120]}..."
    )

    try:
        backend_result = invoke(prompt)
    except Exception as exc:
        if "Timeout" in type(exc).__name__:
            return ChatTurnResult(
                error_message="Grok не ответил вовремя на синтез. Нажми Retry.",
                error_status=504,
                request_id=request_id,
                action="synthesis",
                decision_reason=decision.reason,
            )
        return ChatTurnResult(
            error_message=f"Synthesis error: {exc}",
            error_status=500,
            request_id=request_id,
            action="synthesis",
            decision_reason=decision.reason,
        )

    clean_response, tool_calls, backend_eval = _parse_backend(
        backend_result, allowed_tool_names, log, request_id
    )

    if backend_eval and not backend_eval.ok:
        return ChatTurnResult(
            error_message=backend_eval.message,
            error_status=502,
            request_id=request_id,
            backend=getattr(backend_result, "backend", ""),
            action="synthesis",
            decision_reason=decision.reason,
        )

    if not clean_response and not tool_calls and (backend_result.stdout or "").strip():
        log(f"🔁 SYNTHESIS_JSON_REPAIR (request_id={request_id})")
        try:
            repair_result = invoke(prompt + JSON_REPAIR_SUFFIX, retry=True)
            clean_response, tool_calls, repair_eval = _parse_backend(
                repair_result, allowed_tool_names, log, request_id
            )
            if repair_eval and repair_eval.ok and (clean_response or tool_calls):
                backend_result = repair_result
                backend_eval = repair_eval
        except Exception as exc:
            log(f"❌ SYNTHESIS_REPAIR_FAILED: {exc}")

    clean_response, tool_calls = synthesis_output_to_kilo(clean_response, tool_calls, tools)
    clean_response, tool_calls = coerce_text_to_completion(
        clean_response, tool_calls, tools, messages
    )
    tool_calls, validation_err = validate_outbound_tool_calls(tool_calls, tools)
    if validation_err and tools:
        ev = classify_parse_failure(bool(backend_result.stdout))
        return ChatTurnResult(
            error_message=ev.message,
            error_status=502,
            request_id=request_id,
            backend=getattr(backend_result, "backend", ""),
            action="synthesis",
            decision_reason=decision.reason,
        )

    if not clean_response and not tool_calls:
        ev = classify_parse_failure(bool(backend_result.stdout))
        return ChatTurnResult(
            error_message=ev.message,
            error_status=502,
            request_id=request_id,
            backend=getattr(backend_result, "backend", ""),
            action="synthesis",
            decision_reason=decision.reason,
        )

    cache_ok = should_cache_response(backend_eval)
    return ChatTurnResult(
        content=clean_response,
        tool_calls=tool_calls,
        cache=cache_ok and bool(clean_response or tool_calls),
        request_id=request_id,
        backend=getattr(backend_result, "backend", ""),
        action="synthesis",
        decision_reason=decision.reason,
    )


def process_chat_turn(
    messages: list,
    tools: list | None,
    *,
    log: LogFn,
    invoke_synthesis: InvokeFn,
    request_id: str = "",
) -> ChatTurnResult:
    """Process one Kilo turn under synthesis-only orchestrator."""
    t0 = time.time()
    if not request_id:
        request_id = f"req-{int(time.time() * 1000)}"

    allowed_tool_names = [
        (t.get("function", t) or {}).get("name", "")
        for t in (tools or [])
    ]
    allowed_tool_names = [n for n in allowed_tool_names if n]

    if not synthesis_orchestrator_enabled():
        return ChatTurnResult(
            error_message="GROK_ORCHESTRATOR must be synthesis — legacy path disabled on this branch",
            error_status=500,
            request_id=request_id,
            total_s=time.time() - t0,
        )

    decision = orchestrate_turn(messages, tools)
    log(
        f"📥 ORCHESTRATE (request_id={request_id}, action={decision.action}, "
        f"reason={decision.reason}, intent={detect_intent(messages, tools)}, "
        f"kind={decision.synthesis_kind})"
    )

    if decision.action in ("recover", "mechanical"):
        result = ChatTurnResult(
            content=decision.content,
            tool_calls=list(decision.tool_calls or []),
            cache=True,
            request_id=request_id,
            action=decision.action,
            decision_reason=decision.reason,
            total_s=time.time() - t0,
        )
        if result.tool_calls:
            log(f"⚙️ {decision.action.upper()} → {result.tool_calls[0]['function']['name']}")
        return result

    if decision.action == "synthesis":
        result = _run_synthesis(
            messages,
            tools,
            decision,
            allowed_tool_names,
            log,
            invoke_synthesis,
            request_id,
        )
        result.total_s = time.time() - t0
        if result.tool_calls:
            log(
                f"🏁 SYNTHESIS_DONE (request_id={request_id}, backend={result.backend}, "
                f"tools={len(result.tool_calls)}, total={result.total_s:.2f}s)"
            )
        elif result.content:
            log(
                f"🏁 SYNTHESIS_DONE (request_id={request_id}, backend={result.backend}, "
                f"len={len(result.content)}, total={result.total_s:.2f}s)"
            )
        return result

    return ChatTurnResult(
        error_message="Orchestrator could not decide this turn",
        error_status=500,
        request_id=request_id,
        total_s=time.time() - t0,
    )


def failure_as_kilo_tool(
    tools: list | None,
    message: str,
) -> ChatTurnResult | None:
    synthesized = synthesize_backend_failure_response(tools, message)
    if not synthesized:
        return None
    content, tool_calls = synthesized
    return ChatTurnResult(content=content, tool_calls=tool_calls, cache=False)
