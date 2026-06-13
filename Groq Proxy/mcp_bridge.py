#!/usr/bin/env python3
"""MCP stdio bridge to Grok CLI — parallel path to openai_proxy /v1.

Uses the same backend, response parsing, session store, and phase router as Kilo proxy.
Configure in MCP clients (Kilo, Cursor, etc.) as a stdio server — does NOT replace /v1 for Kilo OpenAI provider.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from typing import Any

from backend import invoke_grok_llm, is_backend_failure
from bridge_guards import classify_backend_result
from paths import log_path
from phase_router import grok_permission_mode_for_phase, resolve_grok_phase
from prompt_pipeline import BACKEND_SYSTEM, prepare_kilo_prompt
from response_pipeline import parse_assistant_response, unwrap_grok_cli_stdout_auto
from session_store import get_session_store, resume_sessions_enabled

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "grok-bridge"
SERVER_VERSION = "2.0.0"

_grok_call_lock = threading.Lock()
_BRIDGE_LOG = log_path("mcp_bridge.log")


def _env_flag(name: str, default: str = "1") -> bool:
    return (os.environ.get(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def mcp_bridge_enabled() -> bool:
    return _env_flag("GROK_MCP_BRIDGE", "1")


def bridge_log(msg: str) -> None:
    line = f"[mcp] {msg}\n"
    try:
        with open(_BRIDGE_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _mcp_text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _mcp_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _mcp_result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _unwrap_backend_stdout(raw_stdout: str) -> tuple[str, dict[str, str | None]]:
    output_fmt = os.environ.get("GROK_OUTPUT_FORMAT", "plain")
    parse_text, meta = unwrap_grok_cli_stdout(raw_stdout, output_fmt)
    if not meta.get("session_id") and raw_stdout.strip().startswith("{"):
        parse_text, meta = unwrap_grok_cli_stdout(raw_stdout, "json")
    return parse_text, meta


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "grok_complete",
            "description": (
                "Run one Grok CLI turn (max-turns 1) via the terminal bridge. "
                "Returns assistant text and optional parsed tool_calls JSON."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "User/task prompt for this turn"},
                    "system": {"type": "string", "description": "Optional extra system instructions"},
                    "session_id": {
                        "type": "string",
                        "description": "Optional grok sessionId for --resume",
                    },
                    "conversation_key": {
                        "type": "string",
                        "description": "Optional stable thread key; auto-resume when stored",
                    },
                    "tools_json": {
                        "type": "string",
                        "description": "Optional JSON array of OpenAI-style tool definitions",
                    },
                },
                "required": ["prompt"],
            },
        },
        {
            "name": "grok_proxy_health",
            "description": "Check the OpenAI-compatible proxy at http://localhost:8080/v1/health",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "grok_session_map",
            "description": "Return count of active Kilo↔grok session mappings (resume store)",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def _invoke_grok_locked(
    prompt: str,
    *,
    resume_session_id: str | None = None,
    permission_mode: str | None = None,
):
    _grok_call_lock.acquire()
    try:
        return invoke_grok_llm(
            prompt,
            resume_session_id=resume_session_id,
            permission_mode=permission_mode,
        )
    finally:
        _grok_call_lock.release()


def _build_prompt(
    prompt: str,
    system: str | None,
    tools: list | None,
) -> str:
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    built = prepare_kilo_prompt(messages, tools=tools)
    if built:
        return built
    blocks = [f"SYSTEM:\n{BACKEND_SYSTEM}", f"USER: {prompt}"]
    return "\n\n".join(blocks)


def _format_assistant_payload(content: str | None, tool_calls: list) -> str:
    payload = {"content": content, "tool_calls": []}
    for tc in tool_calls or []:
        fn = tc.get("function", {}) or {}
        args_raw = fn.get("arguments", "{}")
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            args = {}
        payload["tool_calls"].append({"name": fn.get("name"), "arguments": args})
    return json.dumps(payload, ensure_ascii=False, indent=2)


def handle_grok_complete(arguments: dict[str, Any]) -> str:
    prompt = (arguments.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    system = (arguments.get("system") or "").strip() or None
    session_id = (arguments.get("session_id") or "").strip() or None
    conv_key = (arguments.get("conversation_key") or "").strip() or None
    tools: list | None = None
    tools_json = arguments.get("tools_json")
    if tools_json:
        parsed = json.loads(tools_json) if isinstance(tools_json, str) else tools_json
        if isinstance(parsed, list):
            tools = parsed

    if not session_id and conv_key and resume_sessions_enabled():
        session_id = get_session_store().get(conv_key)

    messages = [{"role": "user", "content": prompt}]
    phase = resolve_grok_phase(messages, tools)
    permission_mode = grok_permission_mode_for_phase(phase)
    full_prompt = _build_prompt(prompt, system, tools)

    bridge_log(
        f"grok_complete phase={phase} resume={bool(session_id)} len={len(full_prompt)}"
    )
    result = _invoke_grok_locked(
        full_prompt,
        resume_session_id=session_id,
        permission_mode=permission_mode,
    )
    raw_stdout = result.stdout or ""
    parse_text, meta = unwrap_grok_cli_stdout_auto(raw_stdout)
    eval_result = classify_backend_result(
        result,
        parse_text=parse_text,
        grok_meta=meta,
    )
    if not eval_result.ok or is_backend_failure(result):
        raise RuntimeError(eval_result.message or (result.stderr or "backend failed")[:300])

    allowed = [
        (t.get("function", t) or {}).get("name", "")
        for t in (tools or [])
    ]
    allowed = [n for n in allowed if n]
    content, tool_calls = parse_assistant_response(
        parse_text or result.stderr,
        allowed_tool_names=allowed or None,
    )
    new_session = meta.get("session_id")
    if new_session and conv_key and resume_sessions_enabled():
        get_session_store().set(conv_key, new_session)

    lines = [
        _format_assistant_payload(content, tool_calls),
        "",
        f"backend={result.backend} elapsed_s={result.elapsed_s}",
    ]
    if new_session:
        lines.append(f"session_id={new_session}")
    if conv_key:
        lines.append(f"conversation_key={conv_key}")
    return "\n".join(lines)


def handle_grok_proxy_health() -> str:
    url = os.environ.get("GROK_PROXY_HEALTH_URL", "http://localhost:8080/v1/health")
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return body
    except (urllib.error.URLError, OSError) as e:
        return json.dumps({"status": "down", "error": str(e)}, ensure_ascii=False)


def handle_grok_session_map() -> str:
    return json.dumps(
        {
            "resume_enabled": resume_sessions_enabled(),
            "active_sessions": get_session_store().count(),
        },
        ensure_ascii=False,
        indent=2,
    )


def handle_tools_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "grok_complete":
        text = handle_grok_complete(arguments or {})
        return _mcp_text_content(text)
    if name == "grok_proxy_health":
        return _mcp_text_content(handle_grok_proxy_health())
    if name == "grok_session_map":
        return _mcp_text_content(handle_grok_session_map())
    raise ValueError(f"Unknown tool: {name}")


def handle_prompts_get(params: dict[str, Any]) -> dict[str, Any]:
    """Legacy prompts/get — single text completion for older MCP clients."""
    prompt = (params.get("prompt") or params.get("name") or "").strip()
    system = (params.get("system") or "").strip() or None
    if not prompt:
        prompt = "(Awaiting user input.)"
    text = handle_grok_complete({"prompt": prompt, "system": system})
    return {
        "messages": [
            {"role": "assistant", "content": {"type": "text", "text": text}},
        ],
    }


def dispatch_request(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return _mcp_result(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return _mcp_result(req_id, {})

    if method == "tools/list":
        return _mcp_result(req_id, {"tools": tool_definitions()})

    if method == "tools/call":
        params = req.get("params", {}) or {}
        name = params.get("name", "")
        try:
            result = handle_tools_call(name, params.get("arguments") or {})
            return _mcp_result(req_id, result)
        except Exception as e:
            bridge_log(f"tools/call error {name}: {e}")
            return _mcp_result(
                req_id,
                {
                    "content": [{"type": "text", "text": f"error: {e}"}],
                    "isError": True,
                },
            )

    if method == "prompts/list":
        return _mcp_result(
            req_id,
            {
                "prompts": [
                    {
                        "name": "grok_chat",
                        "description": "Legacy single-shot Grok prompt (uses grok_complete internally)",
                        "arguments": [
                            {
                                "name": "prompt",
                                "description": "User message",
                                "required": True,
                            },
                        ],
                    },
                ],
            },
        )

    if method == "prompts/get":
        params = req.get("params", {}) or {}
        try:
            return _mcp_result(req_id, handle_prompts_get(params))
        except Exception as e:
            bridge_log(f"prompts/get error: {e}")
            return _mcp_error(req_id, -32000, str(e))

    if req_id is None:
        return None
    return _mcp_error(req_id, -32601, f"Method not found: {method}")


def run_stdio_server() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass

    bridge_log("stdio server started")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = dispatch_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as e:
            bridge_log(f"unhandled: {e}")
            err = _mcp_error(None, -32000, str(e))
            sys.stdout.write(json.dumps(err, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
