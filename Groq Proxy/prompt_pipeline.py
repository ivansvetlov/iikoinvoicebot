"""Kilo Code prompt compression and offload resolution."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any


DEFAULT_MAX_PROMPT_CHARS = 32_000
MAX_HISTORY_MESSAGES = 8

BACKEND_SYSTEM = """You are the autonomous LLM brain for Kilo Code IDE.
Kilo executes ALL tools locally — you only DECIDE which tool to call next.
You MUST NOT execute tools yourself.

AUTONOMOUS RULES (user phrasing does not matter — interpret intent freely):
- Greeting/status → attempt_completion with brief reply.
- Analyze/review/project questions → read_file or list_files FIRST (never guess file contents).
- Plan/design → read relevant files if needed, then attempt_completion with the plan.
- Implement/fix → read_file / write_to_file / execute_command as appropriate, one tool per turn.
- After TOOL RESULT in history → continue with next tool OR attempt_completion when truly done.

Always exactly ONE tool per response when tools are listed. Output ONLY JSON — no thinking text."""

_KILO_STRIP_PATTERNS = [
    r"<environment_details>[\s\S]*?</environment_details>",
    r"====\s*USER'S CUSTOM INSTRUCTIONS\s*====[\s\S]*?====\s*END CUSTOM INSTRUCTIONS\s*====",
    r"TOOL USE\s*You have access to[\s\S]*?Tool Use Guidelines",
    r"CAPABILITIES\s*-\s*You have access to[\s\S]*?RULES",
]

_PROMPT_FILE_RE = re.compile(
    r"(?:\\?\?\\)?[A-Za-z]:\\(?:[^\s\n]+\\)*prompts\\prompt_(\d+)\.txt",
    re.IGNORECASE,
)


_INTENT_GREETING = (
    "работаешь", "работает", "ты тут", "ping", "hello", "hi", "hey", "привет",
    "are you there", "are you working", "ты здесь", "на связи",
)
_INTENT_ANALYSIS = (
    "анализ", "analyze", "проанализ", "разбер", "оцени", "review", "изучи",
    "look at", "what do you think", "как тебе", "что думаешь", "посмотри",
    "исследуй", "inspect", "audit",
)
_INTENT_PLAN = (
    "план", "plan", "спланир", "roadmap", "архитектур", "design doc", "стратег",
)
_READ_TOOL_NAMES = ("read_file", "read_files", "file_read")
_LIST_TOOL_NAMES = ("list_files", "list_dir", "filesystem_list", "ls")


def _latest_user_intent(messages: list) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") != "user":
            continue
        text = normalize_message_content(msg.get("content"))
        text = _ENV_DETAILS_RE.sub("", text).strip()
        task_m = re.search(r"<task>(.*?)</task>", text, re.DOTALL | re.IGNORECASE)
        if task_m:
            text = task_m.group(1).strip()
        if text and "[error]" not in text.lower():
            return text
    return _last_user_text(messages)


def _pick_tool_by_names(tools: list, names: tuple[str, ...]) -> tuple[str, dict] | None:
    for tool in tools or []:
        fn = tool.get("function", tool) or {}
        name = fn.get("name", "")
        if name in names:
            return name, fn
    return None


def detect_intent(messages: list, tools: list | None = None) -> str:
    if needs_agent_continuation(messages):
        return "continue"
    if is_kilo_tool_error_turn(messages):
        return "tool_error"
    text = _latest_user_intent(messages).lower()
    if not text:
        return "agent"
    if len(text) <= 120 and any(m in text for m in _INTENT_GREETING):
        return "greeting"
    if any(m in text for m in _INTENT_ANALYSIS):
        return "analysis"
    if any(m in text for m in _INTENT_PLAN):
        return "plan"
    return "agent"


def build_intent_instructions(intent: str, tools: list | None) -> str:
    if not tools:
        return 'Reply ONLY JSON: {"content": "your answer", "tool_calls": []}'
    complete = pick_completion_tool(tools)
    read_t = _pick_tool_by_names(tools, _READ_TOOL_NAMES)
    list_t = _pick_tool_by_names(tools, _LIST_TOOL_NAMES)
    read_name = read_t[0] if read_t else "read_file"
    list_name = list_t[0] if list_t else "list_files"
    complete_name = complete[0] if complete else "attempt_completion"

    guides = {
        "greeting": (
            f"INTENT=greeting. Reply via {complete_name} only with a brief friendly answer."
        ),
        "analysis": (
            f"INTENT=analysis. User wants project/code analysis in natural language. "
            f"Do NOT guess — first call {read_name} or {list_name} to load real files. "
            f"Use {complete_name} only in a LATER turn after TOOL RESULTs when you have evidence."
        ),
        "plan": (
            f"INTENT=plan. User wants a plan. Read files with {read_name}/{list_name} if needed, "
            f"then {complete_name} with a structured plan."
        ),
        "continue": (
            f"INTENT=continue. Use TOOL RESULTs in history. Next: another tool if more context needed, "
            f"else {complete_name} with final answer."
        ),
        "tool_error": (
            f"INTENT=tool_error. Kilo requires a tool call. Use {complete_name} with the pending answer."
        ),
        "agent": (
            f"INTENT=agent. Pick the best single tool automatically. "
            f"Need context → {read_name}/{list_name}. Task done → {complete_name}."
        ),
    }
    return guides.get(intent, guides["agent"])



_COMPLETION_TOOL_NAMES = ("attempt_completion", "complete_task", "task_complete")


def normalize_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return str(content)


def _read_offload_file(path: str) -> str | None:
    clean = path.replace("\\\\?\\", "").replace("\\?\\", "")
    if os.path.isfile(clean):
        try:
            with open(clean, encoding="utf-8", errors="replace") as f:
                return f.read().strip()
        except OSError:
            return None
    m = _PROMPT_FILE_RE.search(path)
    if not m:
        return None
    idx = m.group(1)
    base = os.path.expanduser("~/.grok/sessions")
    if not os.path.isdir(base):
        return None
    for root, _dirs, files in os.walk(base):
        if f"prompt_{idx}.txt" in files:
            full = os.path.join(root, f"prompt_{idx}.txt")
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    return f.read().strip()
            except OSError:
                return None
    return None


def resolve_offloaded_prompts(text: str) -> str:
    if not text:
        return text

    def _replace(match: re.Match) -> str:
        path = match.group(0)
        body = _read_offload_file(path)
        if body:
            return f"\n[INLINED OFFLOADED PROMPT]\n{body}\n"
        return path

    return _PROMPT_FILE_RE.sub(_replace, text)


def compress_kilo_system(system_text: str) -> str:
    if not system_text:
        return ""
    text = system_text
    for pat in _KILO_STRIP_PATTERNS:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > 8000:
        text = (
            text[:3500]
            + "\n\n[... Kilo system rules truncated for LLM backend ...]\n\n"
            + text[-1500:]
        )
    return text


def compress_tools_manifest(tools: list) -> str:
    if not tools:
        return ""
    lines = ["AVAILABLE TOOLS (compressed):"]
    for tool in tools:
        fn = tool.get("function", tool)
        name = fn.get("name", "unknown")
        desc = (fn.get("description") or "")[:120]
        params = fn.get("parameters", {})
        props = params.get("properties", {}) if isinstance(params, dict) else {}
        keys = ", ".join(props.keys()) if props else ""
        req = params.get("required", []) if isinstance(params, dict) else []
        req_s = f" required=[{', '.join(req)}]" if req else ""
        lines.append(f"- {name}: {desc} params=({keys}){req_s}")
    return "\n".join(lines)


def build_json_tool_instructions() -> str:
    return """
RESPONSE FORMAT (mandatory):
Reply with ONLY valid JSON, no markdown fences, no extra text:
{"content": "brief assistant text or null", "tool_calls": [{"name": "TOOL_NAME", "arguments": {...}}]}

Rules:
- Use exactly ZERO or ONE tool call per response.
- "name" must match one of AVAILABLE TOOLS.
- "arguments" must be a JSON object matching that tool's parameters.
- Do NOT execute tools yourself. Only emit the JSON decision for the client.
- If tools are listed and the task is done (greeting/status/answer), use attempt_completion — never tool_calls: [].
- If no tools are listed, use "tool_calls": [].
"""


def format_messages_for_prompt(messages: list, include_system: bool = False) -> str:
    out = []
    for msg in messages or []:
        role = msg.get("role", "user")
        if role == "system" and not include_system:
            continue
        content = normalize_message_content(msg.get("content"))

        if role == "assistant" and msg.get("tool_calls"):
            tc_text = []
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                name = fn.get("name", "unknown")
                args = fn.get("arguments", "{}")
                tc_text.append(f'{{"name": "{name}", "arguments": {args}}}')
            prefix = f"ASSISTANT: {content}\n" if content else "ASSISTANT:\n"
            out.append(prefix + "tool_calls: " + ", ".join(tc_text))
            continue

        if role == "tool":
            out.append(f"TOOL RESULT ({msg.get('tool_call_id', 'unknown')}): {content}")
            continue

        out.append(f"{role.upper()}: {content}")
    return "\n\n".join(out).strip()


def _tail_messages(messages: list, limit: int = MAX_HISTORY_MESSAGES) -> list:
    if not messages or len(messages) <= limit:
        return list(messages or [])
    return list(messages[-limit:])


_ENV_DETAILS_RE = re.compile(
    r"<environment_details>[\s\S]*?</environment_details>",
    re.IGNORECASE,
)


def _last_user_text(messages: list) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            text = normalize_message_content(msg.get("content")).strip()
            text = _ENV_DETAILS_RE.sub("", text).strip()
            return text
    return ""


def _real_user_text(messages: list) -> str:
    return _latest_user_intent(messages)


def _user_turn_key(messages: list) -> str:
    text = _latest_user_intent(messages).lower()
    if not text:
        return ""
    tail_roles = ",".join(m.get("role", "?") for m in (messages or [])[-5:])
    return f"{text[:200]}|n={len(messages or [])}|{tail_roles}"


def already_answered_last_user(messages: list) -> bool:
    """True only when Kilo retries the same user turn (last message is user)."""
    if not messages or messages[-1].get("role") != "user":
        return False

    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        return False

    for msg in messages[last_user_idx + 1 :]:
        role = msg.get("role")
        if role == "tool":
            return False
        if role == "assistant":
            if msg.get("tool_calls"):
                return True
            if normalize_message_content(msg.get("content")).strip():
                return True
    return False


def needs_agent_continuation(messages: list) -> bool:
    return bool(messages) and messages[-1].get("role") == "tool"


def pick_completion_tool(tools: list) -> tuple[str, dict] | None:
    by_name: dict[str, dict] = {}
    for tool in tools or []:
        fn = tool.get("function", tool) or {}
        name = fn.get("name", "")
        if name:
            by_name[name] = fn
    for name in _COMPLETION_TOOL_NAMES:
        if name in by_name:
            return name, by_name[name]
    for name, fn in by_name.items():
        low = name.lower()
        if "completion" in low or low in ("respond", "finish"):
            return name, fn
    return None


def completion_argument_key(fn: dict) -> str:
    props = (fn.get("parameters") or {}).get("properties") or {}
    for key in ("result", "message", "response", "text", "content"):
        if key in props:
            return key
    return next(iter(props), "result")


def build_completion_tool_call(tool_name: str, fn: dict, text: str) -> dict:
    key = completion_argument_key(fn)
    return {
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps({key: text}, ensure_ascii=False),
        },
    }


def is_kilo_tool_error_turn(messages: list) -> bool:
    text = _last_user_text(messages).lower()
    return "[error]" in text and "did not use a tool" in text


def last_assistant_text(messages: list) -> str | None:
    for msg in reversed(messages or []):
        if msg.get("role") != "assistant":
            continue
        if msg.get("tool_calls"):
            continue
        text = normalize_message_content(msg.get("content")).strip()
        if text:
            return text
    return None


def synthesize_tool_error_response(
    messages: list,
    tools: list | None,
) -> tuple[str | None, list] | None:
    if not is_kilo_tool_error_turn(messages) or not tools:
        return None
    picked = pick_completion_tool(tools)
    if not picked:
        return None
    text = last_assistant_text(messages)
    if not text:
        return None
    name, fn = picked
    return None, [build_completion_tool_call(name, fn, text)]


def coerce_text_to_completion(
    content: str | None,
    tool_calls: list,
    tools: list | None,
    messages: list,
) -> tuple[str | None, list]:
    if tool_calls or not tools:
        return content, tool_calls
    picked = pick_completion_tool(tools)
    if not picked:
        return content, tool_calls
    name, fn = picked
    if is_kilo_tool_error_turn(messages):
        text = last_assistant_text(messages) or content or "OK"
        return None, [build_completion_tool_call(name, fn, text)]
    if is_simple_user_turn(messages) and content:
        return None, [build_completion_tool_call(name, fn, content)]
    return content, tool_calls


def is_simple_user_turn(messages: list) -> bool:
    if not messages or messages[-1].get("role") != "user":
        return False
    if is_kilo_tool_error_turn(messages):
        return False
    text = _latest_user_intent(messages).lower()
    if len(text) > 120:
        return False
    markers = (
        "работаешь", "работает", "ты тут", "ping", "hello", "hi", "hey",
        "are you there", "are you working", "ты здесь", "на связи",
    )
    return any(m in text for m in markers)


def prepare_kilo_prompt(
    messages: list,
    tools: list | None = None,
    max_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> str:
    history = _tail_messages(messages)
    conv = format_messages_for_prompt(history, include_system=False)
    conv = resolve_offloaded_prompts(conv)

    blocks = [f"SYSTEM:\n{BACKEND_SYSTEM}"]
    if conv:
        blocks.append(conv)
    if tools:
        intent = detect_intent(messages, tools)
        blocks.append(compress_tools_manifest(tools))
        blocks.append(build_json_tool_instructions())
        blocks.append(build_intent_instructions(intent, tools))
    else:
        blocks.append(
            'Reply ONLY JSON: {"content": "your brief answer", "tool_calls": []}'
        )

    prompt = "\n\n".join(blocks).strip()
    prompt = resolve_offloaded_prompts(prompt)
    return apply_budget(prompt, max_chars)


def apply_budget(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.65)
    tail = int(max_chars * 0.25)
    return (
        text[:head]
        + f"\n\n[... truncated {len(text) - head - tail} chars for LLM budget ...]\n\n"
        + text[-tail:]
    )
