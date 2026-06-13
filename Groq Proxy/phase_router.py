"""Two-phase grok routing: planner (read-only) vs agent (write/exec) vs recovery."""

from __future__ import annotations

import os

from prompt_pipeline import (
    _EXEC_TOOL_NAMES,
    _READ_TOOL_NAMES,
    _LIST_TOOL_NAMES,
    _WRITE_TOOL_NAMES,
    detect_intent,
    is_kilo_tool_error_turn,
    normalize_message_content,
)

Phase = str  # "planner" | "agent" | "recovery"


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def two_phase_enabled() -> bool:
    return _env_flag("GROK_TWO_PHASE", "0")


def _last_executed_tool_name(messages: list) -> str | None:
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
        if tc_id and tc_id in tool_names:
            return tool_names[tc_id]
    return None


def _user_wants_mutation(messages: list) -> bool:
    markers = (
        "создай", "создать", "напиши", "добавь", "измени", "исправь", "удали",
        "implement", "create", "write", "fix", "edit", "add", "delete", "run ",
        "execute", "выполни", "запусти",
    )
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        text = normalize_message_content(msg.get("content")).lower()
        if any(m in text for m in markers):
            return True
        break
    return False


def resolve_grok_phase(messages: list, tools: list | None) -> Phase:
    if is_kilo_tool_error_turn(messages):
        return "recovery"
    if _user_wants_mutation(messages):
        return "agent"
    intent = detect_intent(messages, tools)
    if intent in ("greeting", "analysis", "plan"):
        return "planner"
    if intent == "continue":
        last_tool = _last_executed_tool_name(messages)
        if last_tool:
            if last_tool in _WRITE_TOOL_NAMES or last_tool in _EXEC_TOOL_NAMES:
                return "agent"
            if last_tool in _READ_TOOL_NAMES or last_tool in _LIST_TOOL_NAMES:
                return "planner"
        return "agent"
    return "planner"


def passive_cli_mode() -> bool:
    return _env_flag("GROK_PASSIVE_CLI", "1")


def grok_permission_mode_for_phase(phase: Phase) -> str | None:
    """Kilo phase steers prompt instructions; grok-cli stays passive when enabled."""
    if passive_cli_mode():
        return "plan"
    if not two_phase_enabled():
        return None
    if phase == "planner":
        return "plan"
    return None
