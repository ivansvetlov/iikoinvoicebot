"""Clean acpx/grok output and parse structured tool calls for Kilo."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any


_ACPX_NOISE_PREFIXES = (
    "[client]",
    "[thinking]",
    "[done]",
    "[tool]",
    "[error]",
    "Error handling notification",
)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\"tool_calls\"[\s\S]*\}")
_INLINE_JSON_RE = re.compile(r'\{[^{}]*"tool_calls"\s*:\s*\[[^\]]*\][^{}]*\}')
_CONTENT_JSON_RE = re.compile(r'\{[^{}]*"content"\s*:\s*[^}]+\}')

_LEGACY_TOOL_RE = re.compile(
    r"^tool call\s+(\w+)\s+with\s+(.*?)$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_LEGACY_ARG_RE = re.compile(r"^(\w+)\s+is\s+(.+?)$", re.MULTILINE)

_AGENT_NOISE_MARKERS = (
    "[tool]", "ListDir", "kind: read", "kind: execute", "kind: other",
    "input:", "FileReadError", "<|im_start|>", "<|im_end|>",
    "## Explanation", "First, the user", "hint: rerun",
    '"type": "ListDir"', '"type": "ReadFile"',
)
_CHAT_TEMPLATE_RE = re.compile(r"<\|im_\w+\|>")


def strip_acpx_metadata(raw: str) -> str:
    if not raw:
        return ""

    text = re.sub(
        r"Error handling notification \{[\s\S]*?\}\s*\{[\s\S]*?\}",
        "",
        raw,
    )

    kept = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if any(s.startswith(p) for p in _ACPX_NOISE_PREFIXES):
            continue
        if s.startswith("{") and ("jsonrpc" in s or '"method"' in s):
            continue
        if "FileReadError" in s or "Path is outside allowed cwd" in s:
            continue
        kept.append(s)

    if kept:
        return "\n".join(kept).strip()

    m = re.search(
        r"\[thinking\][^\n]*\n([\s\S]*?)(?=\n\[client\]|\n\[done\]|\Z)",
        raw,
    )
    if m:
        candidate = m.group(1).strip()
        lines = [
            l.strip()
            for l in candidate.splitlines()
            if l.strip() and not l.strip().startswith(_ACPX_NOISE_PREFIXES)
        ]
        if lines:
            return "\n".join(lines).strip()

    return raw.strip()


def _try_parse_json_response(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    for pat in (_JSON_BLOCK_RE, _JSON_OBJECT_RE, _CONTENT_JSON_RE):
        m = pat.search(text)
        if m:
            chunk = m.group(1) if pat is _JSON_BLOCK_RE else m.group(0)
            try:
                obj = json.loads(chunk)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue

    for m in _INLINE_JSON_RE.finditer(text):
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "tool_calls" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _validate_tool_call(name: str, arguments: Any, allowed_names: set[str]) -> dict | None:
    if allowed_names and name not in allowed_names:
        return None
    if not isinstance(arguments, dict):
        return None
    for v in arguments.values():
        if isinstance(v, str):
            if re.search(r"^[A-Za-z]:\\[^\\]{0,3}\.?$", v):
                return None
            if "\\?\\" in v and len(v) < 20:
                return None
    return {
        "id": f"call_{uuid.uuid4().hex[:12]}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def _legacy_extract_tool_calls(text: str, allowed_names: set[str]) -> list[dict]:
    for match in _LEGACY_TOOL_RE.finditer(text):
        name = match.group(1)
        if allowed_names and name not in allowed_names:
            continue
        args_text = match.group(2)
        args: dict[str, Any] = {}
        for arg_m in _LEGACY_ARG_RE.finditer(args_text):
            key = arg_m.group(1)
            val = arg_m.group(2).strip()
            if val.startswith("{") or val.startswith("["):
                try:
                    val = json.loads(val)
                except json.JSONDecodeError:
                    pass
            args[key] = val
        validated = _validate_tool_call(name, args, allowed_names)
        if validated:
            return [validated]
    return []


def _openai_calls_from_parsed(parsed: dict, allowed: set[str]) -> tuple[str | None, list[dict]]:
    content = parsed.get("content")
    if content is not None:
        content = str(content).strip() or None
    tool_calls_raw = parsed.get("tool_calls") or []
    openai_calls = []
    if isinstance(tool_calls_raw, list):
        for tc in tool_calls_raw[:1]:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name") or (tc.get("function") or {}).get("name")
            args = tc.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if name:
                v = _validate_tool_call(name, args, allowed or {name})
                if v:
                    openai_calls.append(v)
    return content, openai_calls


def _dedupe_lines(text: str) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return "\n".join(out).strip()


def _extract_clean_paragraph(cleaned: str) -> str | None:
    candidates: list[str] = []
    for para in re.split(r"\n{2,}", cleaned):
        p = para.strip()
        if not p or len(p) > 800:
            continue
        if any(m in p for m in _AGENT_NOISE_MARKERS):
            continue
        p = _CHAT_TEMPLATE_RE.sub("", p).strip()
        if p.startswith("**") and p.endswith("**"):
            p = p.strip("*").strip()
        if p:
            candidates.append(p)
    if candidates:
        return candidates[-1]
    lines = [
        l.strip()
        for l in cleaned.splitlines()
        if l.strip()
        and not any(m in l for m in _AGENT_NOISE_MARKERS)
        and not l.strip().startswith(("{", "[", "SYSTEM:", "USER:", "ASSISTANT:"))
    ]
    if lines:
        return _dedupe_lines("\n".join(lines[-3:]))
    return None


def grok_wrapper_indicates_failure(
    meta: dict[str, str | None],
    parse_text: str,
) -> str | None:
    """Detect grok-cli agent loop exit with no usable assistant payload."""
    stop = (meta.get("stop_reason") or "").strip().lower()
    text = (parse_text or "").strip()
    if stop in ("cancelled", "canceled", "error", "maxturns", "max_turns"):
        if not text:
            return "wrapper_cancelled_empty"
    if not text and meta.get("session_id") and stop:
        return f"wrapper_empty_{stop}"
    return None


def unwrap_grok_cli_stdout_auto(
    raw: str,
    output_format: str = "plain",
) -> tuple[str, dict[str, str | None]]:
    """Unwrap grok stdout; auto-detect JSON wrapper when env format is plain."""
    parse_text, meta = unwrap_grok_cli_stdout(raw, output_format)
    if not meta.get("session_id") and (raw or "").strip().startswith("{"):
        parse_text, meta = unwrap_grok_cli_stdout(raw, "json")
    return parse_text, meta


def unwrap_grok_cli_stdout(
    raw: str,
    output_format: str = "plain",
) -> tuple[str, dict[str, str | None]]:
    """Extract assistant payload from grok --output-format json wrapper."""
    fmt = (output_format or "plain").strip().lower()
    if fmt != "json" or not (raw or "").strip():
        return raw or "", {}
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError:
        return raw or "", {}
    if not isinstance(outer, dict):
        return raw or "", {}

    text = outer.get("text") or outer.get("content") or ""
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)

    meta = {
        "session_id": outer.get("sessionId") or outer.get("session_id"),
        "stop_reason": outer.get("stopReason") or outer.get("stop_reason"),
        "request_id": outer.get("requestId") or outer.get("request_id"),
    }
    return text.strip(), meta


def parse_assistant_response(
    text: str,
    allowed_tool_names: list[str] | None = None,
) -> tuple[str | None, list[dict]]:
    allowed = set(allowed_tool_names or [])

    parsed = _try_parse_json_response(text)
    cleaned = (text or "").strip()
    if parsed is None:
        cleaned = _dedupe_lines(strip_acpx_metadata(text))
        parsed = _try_parse_json_response(cleaned)

    if parsed is not None:
        return _openai_calls_from_parsed(parsed, allowed)

    legacy = _legacy_extract_tool_calls(cleaned, allowed) if allowed else []
    if legacy:
        content = _LEGACY_TOOL_RE.sub("", cleaned).strip() or None
        return content, legacy

    if cleaned and any(m in cleaned for m in _AGENT_NOISE_MARKERS):
        retry = _try_parse_json_response(text) or _try_parse_json_response(cleaned)
        if retry is not None:
            return _openai_calls_from_parsed(retry, allowed)
        extracted = _extract_clean_paragraph(cleaned)
        if extracted:
            return extracted, []

    if cleaned:
        cleaned = _dedupe_lines(_CHAT_TEMPLATE_RE.sub("", cleaned).strip())
    return cleaned or None, []
