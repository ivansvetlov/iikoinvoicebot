"""Kilo Code prompt compression and offload resolution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


DEFAULT_MAX_PROMPT_CHARS = _env_int("GROK_MAX_PROMPT_CHARS", 40_000)
MAX_HISTORY_MESSAGES = _env_int("GROK_MAX_HISTORY", 12)
MAX_TOOL_RESULT_CHARS = _env_int("GROK_MAX_TOOL_RESULT_CHARS", 6_000)
LONG_SESSION_TOOL_THRESHOLD = _env_int("GROK_LONG_SESSION_TOOLS", 6)

BACKEND_SYSTEM = """You are the autonomous LLM brain for Kilo Code IDE.
Kilo executes ALL tools locally — you only DECIDE which tool to call next.
You MUST NOT execute tools yourself. NEVER use Grok built-in tools (Read, Write, search_replace, Bash, etc.).

AUTONOMOUS RULES (user phrasing does not matter — interpret intent freely):
- Greeting/status → attempt_completion with brief reply.
- Analyze/review/project questions → read_file or list_files FIRST (never guess file contents).
- Plan/design → read relevant files if needed, then attempt_completion with the plan.
- Implement/fix → read_file / write_to_file / execute_command as appropriate, one tool per turn.
- To create or edit files → emit write_to_file (or the matching Kilo edit tool) in JSON; Kilo runs it and shows the diff. Never write files yourself.
- After TOOL RESULT in history → continue with next tool OR attempt_completion when truly done.

Always exactly ONE tool per response when tools are listed. Output ONLY JSON — no thinking text.

MODEL FIDELITY (95–99% Grok identity):
- You are still Grok: deep, precise, technically honest — format rules do not dumb you down.
- In attempt_completion, the result text may be long and detailed when the user asked for depth.
- Prefer evidence from TOOL RESULTs; never fabricate file contents you did not receive."""

PLANNER_ONLY_SUFFIX = """
CRITICAL RECOVERY MODE:
- Reply with ONLY one JSON object for Kilo. No markdown, no prose outside JSON.
- ZERO Grok built-in tools. Do NOT read/write/execute on disk yourself.
- Pick exactly ONE tool from AVAILABLE TOOLS and return it in tool_calls.
- If stuck, use attempt_completion with a short honest status — never end silently.
"""

JSON_REPAIR_SUFFIX = """
JSON REPAIR:
- Your previous output was not usable. Return ONLY one valid JSON object for Kilo.
- Exactly ZERO or ONE entry in tool_calls; name must match AVAILABLE TOOLS.
- No markdown fences, no commentary outside JSON.
"""

CONTINUE_STRICT_SUFFIX = """
CONTINUE MODE (strict):
- Mid-task: emit exactly ONE Kilo tool as JSON. Never use Grok built-in tools.
- If TOOL RESULTs already cover the ask → attempt_completion now (do not read more files).
- write_to_file only when the user explicitly asked to create/edit a file.
"""

LONG_SESSION_SUFFIX = """
LONG SESSION:
- Many steps already done. Summarize progress in attempt_completion when the original task is satisfied.
- Avoid redundant read_file/list_files unless a specific missing file is required.
"""

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
_WRITE_TOOL_NAMES = (
    "write_to_file",
    "write_file",
    "apply_diff",
    "search_and_replace",
    "insert_content",
    "edit_file",
)
_EXEC_TOOL_NAMES = ("execute_command", "run_command", "terminal", "bash", "shell")


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


def detect_intent_flags(text: str) -> dict[str, bool]:
    low = (text or "").lower()
    return {
        "greeting": any(m in low for m in _INTENT_GREETING),
        "analysis": any(m in low for m in _INTENT_ANALYSIS),
        "plan": any(m in low for m in _INTENT_PLAN),
    }


def detect_intent(messages: list, tools: list | None = None) -> str:
    if needs_agent_continuation(messages):
        return "continue"
    if is_kilo_tool_error_turn(messages):
        return "tool_error"
    text = _latest_user_intent(messages).lower()
    if not text:
        return "agent"
    flags = detect_intent_flags(text)
    mutation_markers = (
        "создай", "создать", "напиши", "добавь", "измени", "исправь", "удали",
        "implement", "create", "write", "fix", "edit", "add", "delete",
        "execute", "выполни", "запусти",
    )
    if any(m in text for m in mutation_markers):
        return "agent"
    if flags["analysis"]:
        return "analysis"
    if flags["plan"]:
        return "plan"
    if flags["greeting"] and len(text) <= 120:
        return "greeting"
    return "agent"


def build_intent_instructions(
    intent: str,
    tools: list | None,
    flags: dict[str, bool] | None = None,
) -> str:
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
    guide = guides.get(intent, guides["agent"])
    if flags and flags.get("greeting") and (flags.get("analysis") or flags.get("plan")):
        guide += (
            " Mixed greeting+task: skip small-talk tools; prioritize the task. "
            f"Brief greeting may appear inside {complete_name} at the end only."
        )
    return guide



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


def trim_tool_result_text(content: str, max_chars: int = MAX_TOOL_RESULT_CHARS) -> str:
    text = (content or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.7)
    tail = int(max_chars * 0.2)
    omitted = len(text) - head - tail
    return (
        text[:head]
        + f"\n\n[... tool result truncated, {omitted} chars omitted ...]\n\n"
        + text[-tail:]
    )


def count_tool_results(messages: list) -> int:
    return sum(1 for m in (messages or []) if m.get("role") == "tool")


def _first_task_user_message(messages: list) -> dict | None:
    for msg in messages or []:
        if msg.get("role") != "user":
            continue
        text = normalize_message_content(msg.get("content")).strip()
        text = _ENV_DETAILS_RE.sub("", text).strip()
        low = text.lower()
        if low and not ("[error]" in low and "did not use a tool" in low):
            return msg
    return None


def build_smart_history(messages: list) -> list:
    """Keep the original user task + recent tail; trim fat tool results."""
    msgs = list(messages or [])
    if len(msgs) <= MAX_HISTORY_MESSAGES:
        return [_trim_message_for_prompt(m) for m in msgs]

    anchor = _first_task_user_message(msgs)
    tail = msgs[-(MAX_HISTORY_MESSAGES - 1) :]
    if anchor and anchor not in tail:
        return [_trim_message_for_prompt(anchor)] + [_trim_message_for_prompt(m) for m in tail]
    return [_trim_message_for_prompt(m) for m in tail]


def _trim_message_for_prompt(msg: dict) -> dict:
    if msg.get("role") != "tool":
        return msg
    trimmed = dict(msg)
    trimmed["content"] = trim_tool_result_text(normalize_message_content(msg.get("content")))
    return trimmed


def format_messages_for_prompt(messages: list, include_system: bool = False) -> str:
    out = []
    for msg in messages or []:
        role = msg.get("role", "user")
        if role == "system" and not include_system:
            continue
        content = normalize_message_content(msg.get("content"))
        if role == "tool":
            content = trim_tool_result_text(content)

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


def conversation_key(messages: list) -> str:
    """Stable id for a Kilo chat thread (first user task)."""
    anchor = _first_task_user_message(messages)
    if not anchor:
        return ""
    text = normalize_message_content(anchor.get("content")).strip()
    text = _ENV_DETAILS_RE.sub("", text).strip()
    task_m = re.search(r"<task>(.*?)</task>", text, re.DOTALL | re.IGNORECASE)
    if task_m:
        text = task_m.group(1).strip()
    if not text:
        return ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:16]


def is_grok_resume_turn(messages: list) -> bool:
    """Follow-up in an ongoing Kilo chat (not the opening user turn)."""
    if not messages or len(messages) < 2:
        return False
    if needs_agent_continuation(messages):
        return True
    if messages[-1].get("role") != "user":
        return False
    for msg in reversed(messages[:-1]):
        role = msg.get("role")
        if role == "assistant":
            return True
        if role == "tool":
            return True
    return False


def build_resume_delta_prompt(
    messages: list,
    tools: list | None = None,
    max_chars: int | None = None,
) -> str:
    """Short prompt for grok --resume; grok session retains prior turns."""
    budget = max_chars if max_chars is not None else DEFAULT_MAX_PROMPT_CHARS
    tail = list(messages or [])[-4:]
    conv = format_messages_for_prompt(tail, include_system=False)
    conv = resolve_offloaded_prompts(conv)
    intent = detect_intent(messages, tools)
    blocks = [
        f"SYSTEM:\n{BACKEND_SYSTEM}",
        (
            "SESSION CONTINUE (grok --resume is active — prior turns are in grok memory; "
            "respond to the latest message only):"
        ),
    ]
    if conv:
        blocks.append(conv)
    if tools:
        blocks.append(compress_tools_manifest(tools))
        blocks.append(build_json_tool_instructions())
        flags = detect_intent_flags(_latest_user_intent(messages))
        blocks.append(build_intent_instructions(intent, tools, flags))
    else:
        blocks.append(
            'Reply ONLY JSON: {"content": "your brief answer", "tool_calls": []}'
        )
    extra = build_prompt_suffixes(messages, intent)
    if extra:
        blocks.append(extra)
    prompt = "\n\n".join(blocks).strip()
    prompt = resolve_offloaded_prompts(prompt)
    return apply_budget(prompt, budget)


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
    return build_tool_call(tool_name, fn, {key: text})


def _first_string_param(fn: dict, candidates: tuple[str, ...]) -> str:
    props = (fn.get("parameters") or {}).get("properties") or {}
    for key in candidates:
        if key in props:
            return key
    return candidates[0]


def build_tool_call(tool_name: str, fn: dict, arguments: dict) -> dict:
    return {
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def build_kilo_error_tool_response(tools: list | None, message: str) -> list | None:
    picked = pick_completion_tool(tools or [])
    if not picked:
        return None
    name, fn = picked
    return [build_completion_tool_call(name, fn, message)]


def synthesize_backend_failure_response(
    tools: list | None,
    message: str,
) -> tuple[str | None, list] | None:
    """Kilo agent mode needs a tool_call — not a bare HTTP 502."""
    tool_calls = build_kilo_error_tool_response(tools, message)
    if not tool_calls:
        return None
    return None, tool_calls


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


def _last_tool_result_text(messages: list) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "tool":
            return normalize_message_content(msg.get("content"))
    return ""


_ANALYSIS_FILE_HINTS = ("analysis", "progress", "audit", "readme", "improvement")
_PATH_IN_LINE_RE = re.compile(
    r"([\w./\\-]+\.(?:md|txt|py|json|yml|yaml))",
    re.IGNORECASE,
)


def _extract_paths_from_listing(listing: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for line in (listing or "").splitlines():
        s = line.strip().strip("-•* ")
        if not s:
            continue
        match = _PATH_IN_LINE_RE.search(s)
        if match:
            path = match.group(1).replace("\\", "/")
        elif "/" in s or "\\" in s:
            path = s.replace("\\", "/")
        elif "." in s and len(s) < 120:
            path = s
        else:
            continue
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _pick_read_target(messages: list, listing: str) -> str:
    user = _latest_user_intent(messages).lower()
    paths = _extract_paths_from_listing(listing)
    if paths:
        scored: list[tuple[int, str]] = []
        for path in paths:
            low = path.lower()
            score = sum(10 for hint in _ANALYSIS_FILE_HINTS if hint in low)
            if "анализ" in user or "analysis" in user:
                if "analysis" in low or "audit" in low or "improvement" in low:
                    score += 25
            if "progress" in low:
                score += 8
            scored.append((score, path))
        scored.sort(key=lambda item: (-item[0], -len(item[1])))
        return scored[0][1]
    if "анализ" in user or "analysis" in user or "audit" in user:
        return "ANALYSIS_AND_IMPROVEMENTS.md"
    return "README.md"


def synthesize_continue_tool(
    messages: list,
    tools: list | None,
) -> tuple[str | None, list] | None:
    """Deterministic next tool after list_files — avoids grok-cli agent-loop on continue."""
    if not tools or not needs_agent_continuation(messages):
        return None
    last_tool = _last_executed_tool_name(messages)
    if last_tool not in _LIST_TOOL_NAMES:
        return None
    intent = detect_intent(messages, tools)
    if intent not in ("continue", "analysis", "plan", "agent"):
        return None
    read_t = _pick_tool_by_names(tools, _READ_TOOL_NAMES)
    if not read_t:
        return None
    name, fn = read_t
    key = _first_string_param(fn, ("path", "file", "filepath", "target_file"))
    target = _pick_read_target(messages, _last_tool_result_text(messages))
    return None, [build_tool_call(name, fn, {key: target})]


def synthesize_intent_first_tool(
    messages: list,
    tools: list | None,
) -> tuple[str | None, list] | None:
    if not tools or messages[-1].get("role") != "user":
        return None
    if needs_agent_continuation(messages) or is_kilo_tool_error_turn(messages):
        return None
    intent = detect_intent(messages, tools)
    if intent not in ("analysis", "plan"):
        return None
    list_t = _pick_tool_by_names(tools, _LIST_TOOL_NAMES)
    if list_t:
        name, fn = list_t
        key = _first_string_param(fn, ("path", "directory", "dir", "target_directory"))
        return None, [build_tool_call(name, fn, {key: "."})]
    read_t = _pick_tool_by_names(tools, _READ_TOOL_NAMES)
    if read_t:
        name, fn = read_t
        key = _first_string_param(fn, ("path", "file", "filepath", "target_file"))
        return None, [build_tool_call(name, fn, {key: "README.md"})]
    return None


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


def build_task_anchor_block(messages: list) -> str:
    anchor = _first_task_user_message(messages)
    if not anchor:
        return ""
    text = normalize_message_content(anchor.get("content")).strip()
    text = _ENV_DETAILS_RE.sub("", text).strip()
    if not text:
        return ""
    if len(messages or []) <= MAX_HISTORY_MESSAGES:
        return ""
    if len(text) > 800:
        text = text[:800] + "..."
    return f"ORIGINAL USER TASK (anchor, do not lose):\n{text}"


def build_prompt_suffixes(messages: list, intent: str) -> str:
    parts: list[str] = []
    anchor = build_task_anchor_block(messages)
    if anchor:
        parts.append(anchor)
    tool_count = count_tool_results(messages)
    if intent == "continue" and tool_count >= 2:
        parts.append(CONTINUE_STRICT_SUFFIX)
    if tool_count >= LONG_SESSION_TOOL_THRESHOLD:
        parts.append(LONG_SESSION_SUFFIX)
    return "\n".join(parts).strip()


def prepare_kilo_prompt(
    messages: list,
    tools: list | None = None,
    max_chars: int | None = None,
) -> str:
    budget = max_chars if max_chars is not None else DEFAULT_MAX_PROMPT_CHARS
    history = build_smart_history(messages)
    conv = format_messages_for_prompt(history, include_system=False)
    conv = resolve_offloaded_prompts(conv)

    blocks = [f"SYSTEM:\n{BACKEND_SYSTEM}"]
    if conv:
        blocks.append(conv)
    intent = detect_intent(messages, tools)
    flags = detect_intent_flags(_latest_user_intent(messages))
    if tools:
        blocks.append(compress_tools_manifest(tools))
        blocks.append(build_json_tool_instructions())
        blocks.append(build_intent_instructions(intent, tools, flags))
    else:
        blocks.append(
            'Reply ONLY JSON: {"content": "your brief answer", "tool_calls": []}'
        )

    extra = build_prompt_suffixes(messages, intent)
    if extra:
        blocks.append(extra)

    prompt = "\n\n".join(blocks).strip()
    prompt = resolve_offloaded_prompts(prompt)
    return apply_budget(prompt, budget)


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
