"""Synthesis-only orchestrator: proxy owns mechanics, Grok owns final synthesis.

Decision tree (no grok-cli on gather steps):
  user + analysis/plan  → list_files
  tool after list_files → read_file (maybe more reads)
  tool after read_file  → synthesis (single Grok call)
  greeting/simple       → synthesis (no gather)
  tool_error            → recover via attempt_completion
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from prompt_pipeline import (
    _EXEC_TOOL_NAMES,
    _LIST_TOOL_NAMES,
    _READ_TOOL_NAMES,
    _WRITE_TOOL_NAMES,
    _extract_paths_from_listing,
    _first_string_param,
    _last_executed_tool_name,
    _last_tool_result_text,
    _latest_user_intent,
    _pick_tool_by_names,
    build_tool_call,
    count_tool_results,
    detect_intent,
    is_simple_user_turn,
    needs_agent_continuation,
    synthesize_continue_tool,
    synthesize_intent_first_tool,
    synthesize_tool_error_response,
)

Action = Literal["recover", "mechanical", "synthesis", "none"]
MAX_READS_PER_TASK = 3

_SYNTHESIS_DEFAULT = os.environ.get("GROK_ORCHESTRATOR", "synthesis").strip().lower()


def synthesis_orchestrator_enabled() -> bool:
    return _SYNTHESIS_DEFAULT in ("synthesis", "synthesis-only", "1", "true", "on")


@dataclass
class OrchestratorDecision:
    action: Action
    content: str | None = None
    tool_calls: list | None = None
    synthesis_kind: str = "default"
    reason: str = ""


def _count_reads_in_history(messages: list) -> int:
    n = 0
    for msg in messages or []:
        if msg.get("role") != "assistant" or not msg.get("tool_calls"):
            continue
        for tc in msg.get("tool_calls", []):
            name = (tc.get("function") or {}).get("name", "")
            if name in _READ_TOOL_NAMES:
                n += 1
    return n


def _last_listing_text(messages: list) -> str:
    tool_names: dict[str, str] = {}
    for msg in messages or []:
        if msg.get("role") != "assistant" or not msg.get("tool_calls"):
            continue
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {}) or {}
            name = fn.get("name", "")
            tc_id = tc.get("id")
            if name and tc_id:
                tool_names[tc_id] = name
    for msg in reversed(messages or []):
        if msg.get("role") != "tool":
            continue
        tc_id = msg.get("tool_call_id")
        if tc_id and tool_names.get(tc_id) in _LIST_TOOL_NAMES:
            return _last_tool_result_text([msg])
    return ""


def _read_paths_done(messages: list) -> set[str]:
    done: set[str] = set()
    pending: dict[str, str] = {}
    for msg in messages or []:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {}) or {}
                name = fn.get("name", "")
                if name in _READ_TOOL_NAMES:
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            import json
                            obj = json.loads(args)
                        except json.JSONDecodeError:
                            obj = {}
                    else:
                        obj = args if isinstance(args, dict) else {}
                    path = (
                        obj.get("path")
                        or obj.get("file")
                        or obj.get("filepath")
                        or obj.get("target_file")
                        or ""
                    )
                    if path and tc.get("id"):
                        pending[tc["id"]] = str(path).replace("\\", "/")
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id in pending:
                done.add(pending.pop(tc_id))
    return done


def _analysis_targets(messages: list) -> list[str]:
    listing = _last_listing_text(messages)
    paths = _extract_paths_from_listing(listing)
    if not paths:
        return []
    scored: list[tuple[int, str]] = []
    user = _latest_user_intent(messages).lower()
    for path in paths:
        low = path.lower()
        score = 0
        if "analysis" in low or "improvement" in low:
            score += 30
        if "progress" in low:
            score += 15
        if "readme" in low:
            score += 10
        if "анализ" in user and ("analysis" in low or "audit" in low):
            score += 20
        scored.append((score, path))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, p in scored[:4]]


def synthesize_extra_read(messages: list, tools: list | None) -> tuple[str | None, list] | None:
    """Read additional analysis files before synthesis (only after list_files)."""
    if not tools or not needs_agent_continuation(messages):
        return None
    if _last_executed_tool_name(messages) not in _READ_TOOL_NAMES:
        return None
    if not _last_listing_text(messages).strip():
        return None
    if _count_reads_in_history(messages) >= MAX_READS_PER_TASK:
        return None
    intent = detect_intent(messages, tools)
    if intent not in ("continue", "analysis", "plan", "agent"):
        return None
    read_t = _pick_tool_by_names(tools, _READ_TOOL_NAMES)
    if not read_t:
        return None
    done = _read_paths_done(messages)
    for target in _analysis_targets(messages):
        norm = target.replace("\\", "/")
        if norm not in done and norm.lower() not in {d.lower() for d in done}:
            name, fn = read_t
            key = _first_string_param(fn, ("path", "file", "filepath", "target_file"))
            return None, [build_tool_call(name, fn, {key: target})]
    return None


def _user_wants_mutation(messages: list) -> bool:
    markers = (
        "создай", "создать", "напиши", "добавь", "измени", "исправь", "удали",
        "implement", "create", "write", "fix", "edit", "add", "delete",
        "execute", "выполни", "запусти", "перепиши",
    )
    text = _latest_user_intent(messages).lower()
    return any(m in text for m in markers)


def orchestrate_turn(messages: list, tools: list | None) -> OrchestratorDecision:
    """Single decision point for synthesis-only mode."""
    if not messages:
        return OrchestratorDecision("none", reason="empty_messages")

    recovered = synthesize_tool_error_response(messages, tools)
    if recovered:
        content, tcs = recovered
        return OrchestratorDecision("recover", content, tcs, reason="tool_error")

    if needs_agent_continuation(messages):
        last_tool = _last_executed_tool_name(messages)
        if last_tool in _LIST_TOOL_NAMES:
            routed = synthesize_continue_tool(messages, tools)
            if routed:
                content, tcs = routed
                return OrchestratorDecision(
                    "mechanical", content, tcs, reason="after_list_files"
                )
        if last_tool in _READ_TOOL_NAMES:
            extra = synthesize_extra_read(messages, tools)
            if extra:
                content, tcs = extra
                return OrchestratorDecision(
                    "mechanical", content, tcs, reason="extra_read_before_synthesis"
                )
            kind = "post_read"
            if _user_wants_mutation(messages):
                kind = "post_read_mutation"
            return OrchestratorDecision("synthesis", synthesis_kind=kind, reason="reads_complete")
        if last_tool in _WRITE_TOOL_NAMES or last_tool in _EXEC_TOOL_NAMES:
            return OrchestratorDecision(
                "synthesis", synthesis_kind="post_action", reason="after_write_or_exec"
            )
        return OrchestratorDecision("synthesis", synthesis_kind="continue", reason="tool_continue")

    if messages[-1].get("role") != "user":
        return OrchestratorDecision("synthesis", synthesis_kind="default", reason="non_user_tail")

    intent = detect_intent(messages, tools)

    if is_simple_user_turn(messages) and intent == "greeting":
        return OrchestratorDecision("synthesis", synthesis_kind="greeting", reason="simple_greeting")

    if tools and count_tool_results(messages) == 0:
        if intent in ("analysis", "plan"):
            routed = synthesize_intent_first_tool(messages, tools)
            if routed:
                content, tcs = routed
                return OrchestratorDecision(
                    "mechanical", content, tcs, reason="gather_list_for_analysis"
                )
        if intent == "agent" or _user_wants_mutation(messages):
            list_t = _pick_tool_by_names(tools, _LIST_TOOL_NAMES)
            if list_t:
                name, fn = list_t
                key = _first_string_param(fn, ("path", "directory", "dir", "target_directory"))
                return OrchestratorDecision(
                    "mechanical",
                    None,
                    [build_tool_call(name, fn, {key: "."})],
                    reason="gather_list_for_mutation",
                )

    if _count_reads_in_history(messages) > 0:
        kind = "analysis" if intent in ("analysis", "plan") else "default"
        return OrchestratorDecision("synthesis", synthesis_kind=kind, reason="has_reads_in_history")

    if not tools:
        return OrchestratorDecision("synthesis", synthesis_kind="chat", reason="no_tools")

    return OrchestratorDecision("synthesis", synthesis_kind=intent or "default", reason="fallback_synthesis")
