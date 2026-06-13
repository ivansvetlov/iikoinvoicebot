"""Cross-layer guards for Kilo ↔ Grok proxy bridge.

Layers:
  L1 contract   — OpenAI API semantics (success vs error, streaming, tool_calls shape)
  L2 loop       — Kilo owns agent loop; grok-cli must not run builtin tools
  L3 adapter    — prompt/response transform, JSON parse, intent
  L4 memory     — history budget, anchors, tool-result trim
  L5 model      — Grok fidelity vs format compliance
  L6 runtime    — timeouts, health, queue
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_BUILTIN_LEAK_MARKERS = (
    "tool_error",
    "grok-build",
    "search_replace",
    "update_goal",
    "execution_failure",
    "tool_output_error",
)

_LAYER_NAMES = {
    "L1": "contract",
    "L2": "loop",
    "L3": "adapter",
    "L4": "memory",
    "L5": "model",
    "L6": "runtime",
}


@dataclass
class BackendEvaluation:
    ok: bool
    layer: str
    code: str
    message: str
    retry_planner: bool = False
    retry_json: bool = False
    cache_allowed: bool = True


def stderr_indicates_builtin_leak(stderr: str | None) -> bool:
    low = (stderr or "").lower()
    return any(m in low for m in _BUILTIN_LEAK_MARKERS)


def classify_backend_result(result) -> BackendEvaluation:
    """Evaluate grok-cli result before trusting stdout."""
    stderr = result.stderr or ""
    stderr_low = stderr.lower()
    elapsed = getattr(result, "elapsed_s", 0.0)

    if "timeout" in stderr_low:
        return BackendEvaluation(
            ok=False,
            layer="L6",
            code="backend_timeout",
            message="Grok не ответил вовремя. Нажми Retry.",
        )

    if stderr_indicates_builtin_leak(stderr):
        return BackendEvaluation(
            ok=False,
            layer="L2",
            code="builtin_tool_leak",
            message=(
                "Grok CLI ушёл во внутренний agent mode вместо JSON для Kilo. "
                "Нажми Retry — прокси переспросит строже."
            ),
            retry_planner=True,
            cache_allowed=False,
        )

    if "max turns" in stderr_low:
        return BackendEvaluation(
            ok=False,
            layer="L2",
            code="max_turns",
            message="Grok исчерпал лимит шагов. Нажми Retry или упрости задачу.",
            retry_planner=True,
            cache_allowed=False,
        )

    stdout = (result.stdout or "").strip()
    if not stdout:
        if result.returncode != 0:
            return BackendEvaluation(
                ok=False,
                layer="L6",
                code="backend_empty",
                message=f"Grok не вернул ответ. Нажми Retry. ({elapsed:.0f}s)",
                cache_allowed=False,
            )
        return BackendEvaluation(
            ok=False,
            layer="L3",
            code="empty_stdout",
            message="Пустой ответ от Grok. Нажми Retry.",
            retry_json=True,
            cache_allowed=False,
        )

    if stderr.strip() and result.returncode != 0:
        # Non-fatal stderr with stdout — still serve if JSON parses later.
        return BackendEvaluation(ok=True, layer="L3", code="ok_with_stderr", message="")

    return BackendEvaluation(ok=True, layer="L3", code="ok", message="")


def classify_parse_failure(has_raw_text: bool) -> BackendEvaluation:
    if has_raw_text:
        return BackendEvaluation(
            ok=False,
            layer="L3",
            code="json_parse_failed",
            message="Grok вернул не-JSON. Нажми Retry.",
            retry_json=True,
            cache_allowed=False,
        )
    return BackendEvaluation(
        ok=False,
        layer="L3",
        code="empty_parse",
        message="Пустой ответ от Grok. Нажми Retry.",
        cache_allowed=False,
    )


def validate_outbound_tool_calls(
    tool_calls: list | None,
    tools: list | None,
) -> tuple[list, str | None]:
    """L1: ensure OpenAI tool_calls shape before sending to Kilo."""
    if not tool_calls:
        return [], None
    allowed = {
        (t.get("function", t) or {}).get("name", "")
        for t in (tools or [])
    }
    allowed.discard("")

    valid: list = []
    for tc in tool_calls[:1]:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        name = fn.get("name", "")
        args_raw = fn.get("arguments", "{}")
        if allowed and name not in allowed:
            return [], "hallucinated_tool"
        if not name:
            return [], "missing_tool_name"
        try:
            json.loads(args_raw if isinstance(args_raw, str) else json.dumps(args_raw))
        except (json.JSONDecodeError, TypeError):
            return [], "invalid_tool_arguments"
        valid.append(tc)
    return valid, None if valid else "no_valid_tools"


def should_cache_response(evaluation: BackendEvaluation | None) -> bool:
    if evaluation is None:
        return True
    return evaluation.cache_allowed


def log_layer_issue(log_fn, evaluation: BackendEvaluation, request_id: str = "") -> None:
    layer_name = _LAYER_NAMES.get(evaluation.layer, evaluation.layer)
    rid = f" request_id={request_id}" if request_id else ""
    log_fn(
        f"🛡️ GUARD layer={evaluation.layer}({layer_name}) code={evaluation.code}{rid}: "
        f"{evaluation.message[:120]}"
    )
