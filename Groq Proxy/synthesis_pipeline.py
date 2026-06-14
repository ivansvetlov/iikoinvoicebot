"""Grok synthesis prompts — one call with full context, Grok voice preserved."""

from __future__ import annotations

import json
import os

from prompt_pipeline import (
    DEFAULT_MAX_PROMPT_CHARS,
    _latest_user_intent,
    apply_budget,
    build_task_anchor_block,
    compress_tools_manifest,
    detect_intent,
    format_messages_for_prompt,
    pick_completion_tool,
    resolve_offloaded_prompts,
    build_smart_history,
)

SYNTHESIS_SYSTEM = """You are Grok — the same model, personality, depth, and technical honesty as on grok.com.

CONTEXT: Kilo Code IDE already executed tools for you. TOOL RESULT sections below are real file/listing
outputs from the user's machine. You did NOT read the repo yourself — use ONLY what appears in TOOL RESULTs.

YOUR JOB NOW: produce the final answer for the user's task. Not another list_files or read_file —
gathering is done. Synthesize, analyze, plan, or explain using the evidence you were given.

OUTPUT (mandatory): exactly ONE JSON object, no markdown fences, no text outside JSON:
{"content": null, "tool_calls": [{"name": "<tool>", "arguments": {...}}]}

Rules:
- Prefer attempt_completion (or the completion tool from AVAILABLE TOOLS) with a rich "result" field.
- Write long, detailed answers when the user asked for depth, analysis, or recommendations.
- If the user explicitly asked to CREATE or EDIT a file AND you have enough evidence, you may return
  ONE write/edit tool from AVAILABLE TOOLS instead of attempt_completion.
- Never invent file contents not present in TOOL RESULTs.
- Never use Grok built-in tools (Read, Write, Bash, etc.) — only Kilo tool names from AVAILABLE TOOLS.
- Exactly ZERO or ONE tool in tool_calls."""

_KIND_HINTS = {
    "greeting": "Short friendly status reply. Brief but warm — still Grok, not a bot script.",
    "analysis": (
        "Deep technical analysis requested. Structure: findings, risks, strengths, prioritized recommendations. "
        "Cite specific files/evidence from TOOL RESULTs."
    ),
    "plan": "Structured plan with phases, trade-offs, and concrete next steps grounded in TOOL RESULTs.",
    "post_read": "Files were read. Deliver the full answer the user asked for — do not request more reads.",
    "post_read_mutation": (
        "User wants file changes. If evidence is sufficient, emit the appropriate write/edit tool. "
        "Otherwise attempt_completion explaining what is missing."
    ),
    "post_action": "Action completed. Summarize what was done and any follow-ups via attempt_completion.",
    "chat": "Direct answer. No tool gathering was needed.",
}


def build_synthesis_prompt(
    messages: list,
    tools: list | None = None,
    *,
    kind: str = "default",
    max_chars: int | None = None,
) -> str:
    budget = max_chars if max_chars is not None else DEFAULT_MAX_PROMPT_CHARS
    history = build_smart_history(messages)
    conv = format_messages_for_prompt(history, include_system=False)
    conv = resolve_offloaded_prompts(conv)

    blocks = [f"SYSTEM:\n{SYNTHESIS_SYSTEM}"]
    anchor = build_task_anchor_block(messages)
    if anchor:
        blocks.append(anchor)

    user_task = _latest_user_intent(messages).strip()
    if user_task:
        blocks.append(f"USER TASK:\n{user_task}")

    hint = _KIND_HINTS.get(kind) or _KIND_HINTS.get(detect_intent(messages, tools), "")
    if hint:
        blocks.append(f"SYNTHESIS MODE ({kind}):\n{hint}")

    if conv:
        blocks.append(f"CONVERSATION AND TOOL RESULTS:\n{conv}")

    if tools:
        blocks.append(compress_tools_manifest(tools))
        complete = pick_completion_tool(tools)
        cname = complete[0] if complete else "attempt_completion"
        blocks.append(
            f"Return ONE JSON tool call. Default completion tool: {cname}."
        )
    else:
        blocks.append(
            'Return: {"content": "your answer", "tool_calls": []}'
        )

    prompt = "\n\n".join(blocks).strip()
    prompt = resolve_offloaded_prompts(prompt)
    return apply_budget(prompt, budget)


def synthesis_output_to_kilo(
    content: str | None,
    tool_calls: list,
    tools: list | None,
) -> tuple[str | None, list]:
    """Ensure Kilo agent mode always gets a valid single tool_call when tools present."""
    if tool_calls:
        return content, tool_calls[:1]
    if not tools or not (content or "").strip():
        return content, tool_calls
    picked = pick_completion_tool(tools)
    if not picked:
        return content, tool_calls
    name, fn = picked
    from prompt_pipeline import build_completion_tool_call, completion_argument_key
    key = completion_argument_key(fn)
    return None, [build_completion_tool_call(name, fn, content or "")]
