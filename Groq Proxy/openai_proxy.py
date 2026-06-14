#!/usr/bin/env python3
"""
OpenAI-compatible proxy for Grok + Kilo Code (synthesis-only architecture).

Branch: feature/synthesis-only-orchestrator

  Kilo executes tools → proxy gathers context mechanically → Grok synthesizes ONCE.

  - orchestrator.py   — list/read mechanics, synthesis gate
  - synthesis_pipeline.py — Grok-voice final prompts
  - kilo_handler.py   — turn processor
  - backend.invoke_synthesis_llm — acpx passive primary

Run: python start_grok.py --daemon
Listen: http://localhost:8080/v1  (model: grok)
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import json
import time
import re
import sys
import os
import socket
import uuid
import shutil
import tempfile
import threading
from datetime import datetime

from backend import invoke_synthesis_llm
from kilo_handler import failure_as_kilo_tool, process_chat_turn
from orchestrator import synthesis_orchestrator_enabled
from paths import log_path
from prompt_pipeline import (
    normalize_message_content as _normalize_content,
    _user_turn_key,
    already_answered_last_user,
    needs_agent_continuation,
    is_simple_user_turn,
    detect_intent,
    DEFAULT_MAX_PROMPT_CHARS,
)

if sys.platform == "win32" and sys.stdout is not None and sys.stdout.isatty():
    import ctypes
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)

PROXY_LOG_FILE = log_path("proxy_requests.log")
_DEDUP_TTL_S = int(os.environ.get("GROK_DEDUP_TTL_S", "180"))
_GROK_TIMEOUT_S = int(os.environ.get("GROK_TIMEOUT", "180"))
_GROK_RETRY_TIMEOUT_S = int(os.environ.get("GROK_RETRY_TIMEOUT_S", "60"))
_PROMPT_WARN_CHARS = int(os.environ.get("GROK_PROMPT_WARN_CHARS", "28000"))
_recent_turn_answers: dict[str, tuple[float, str | None, list]] = {}
_inflight_turns: dict[str, threading.Event] = {}
_dedup_lock = threading.Lock()
_grok_call_lock = threading.Lock()
_proxy_started_at = time.time()


def write_openai_sse_stream(wfile, content: str | None, tool_calls: list, finish_reason: str):
    """OpenAI-compatible SSE sequence so Kilo Code stops loading properly."""
    chunk_id = f"chatcmpl-{int(time.time())}"
    created = int(time.time())

    def _emit(delta: dict, finish: str | None = None) -> bool:
        payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "grok",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return _safe_write(
            wfile,
            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"),
        )

    if not _emit({"role": "assistant"}, None):
        return

    if content:
        # Kilo expects string content deltas; send in one chunk for short replies.
        _emit({"content": content}, None)

    for i, tc in enumerate(tool_calls):
        fn = tc.get("function", {})
        name = fn.get("name", "")
        args = fn.get("arguments", "{}")
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        _emit({
            "tool_calls": [{
                "index": i,
                "id": tc["id"],
                "type": "function",
                "function": {"name": name},
            }]
        }, None)
        if args:
            _emit({
                "tool_calls": [{
                    "index": i,
                    "function": {"arguments": args},
                }]
            }, None)

    _emit({}, finish_reason)
    _safe_write(wfile, b"data: [DONE]\n\n")


def _message_roles_summary(messages: list) -> str:
    return ",".join(m.get("role", "?") for m in (messages or []))


def _get_cached_response(turn_key: str) -> tuple[str | None, list] | None:
    if not turn_key:
        return None
    now = time.time()
    with _dedup_lock:
        cached = _recent_turn_answers.get(turn_key)
    if cached and now - cached[0] < _DEDUP_TTL_S:
        return cached[1], list(cached[2])
    return None


def _should_suppress_duplicate(messages: list) -> str | None:
    """Return suppression reason, or None when Grok should answer normally."""
    turn_key = _user_turn_key(messages)

    # Risk #7: Kilo sometimes fires parallel identical continue requests.
    if needs_agent_continuation(messages):
        if turn_key and _get_cached_response(turn_key) is not None:
            return "continue_duplicate_cached"
        return None
    if not turn_key:
        return None

    # Only dedupe rapid Kilo retries on greeting/status turns (last msg = user).
    if messages[-1].get("role") != "user":
        return None

    if already_answered_last_user(messages):
        return "history_has_assistant_reply"

    if is_simple_user_turn(messages) and _get_cached_response(turn_key) is not None:
        return "recent_duplicate_turn"
    return None


def _begin_turn(turn_key: str) -> threading.Event | None:
    """Leader gets None; followers get an Event to wait on."""
    if not turn_key:
        return None
    with _dedup_lock:
        inflight = _inflight_turns.get(turn_key)
        if inflight is not None:
            return inflight
        _inflight_turns[turn_key] = threading.Event()
        return None


def _release_turn(
    turn_key: str,
    content: str | None = None,
    tool_calls: list | None = None,
    *,
    cache: bool = False,
) -> None:
    if not turn_key:
        return
    with _dedup_lock:
        if cache and (content or tool_calls):
            _recent_turn_answers[turn_key] = (
                time.time(),
                content,
                list(tool_calls or []),
            )
        evt = _inflight_turns.pop(turn_key, None)
    if evt is not None:
        evt.set()


def _wait_for_turn(turn_key: str, evt: threading.Event) -> tuple[str | None, list] | None:
    if evt.wait(timeout=190):
        return _get_cached_response(turn_key)
    return None


def _invoke_synthesis_locked(prompt: str, *, retry: bool = False):
    wait_started = None
    if not _grok_call_lock.acquire(blocking=False):
        wait_started = time.time()
        log("⏳ SYNTHESIS_QUEUE_WAIT")
        _grok_call_lock.acquire()
        waited = time.time() - wait_started
        if waited >= 3:
            log(f"⏳ SYNTHESIS_QUEUE_WAIT done ({waited:.1f}s)")
    try:
        if len(prompt) >= _PROMPT_WARN_CHARS:
            log(f"⚠️ LARGE_SYNTHESIS_PROMPT len={len(prompt)}")
        return invoke_synthesis_llm(prompt, retry=retry)
    finally:
        _grok_call_lock.release()


_CLIENT_GONE_WINERRORS = frozenset({10053, 10054})


def _client_gone(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
        return True
    if isinstance(exc, OSError):
        winerr = getattr(exc, "winerror", None)
        if winerr in _CLIENT_GONE_WINERRORS:
            return True
    return False


def _safe_write(wfile, data: bytes) -> bool:
    try:
        wfile.write(data)
        wfile.flush()
        return True
    except Exception as exc:
        if _client_gone(exc):
            log(f"⚠️ CLIENT_DISCONNECTED during write: {exc}")
            return False
        raise


def _send_provider_error(handler, status: int, message: str) -> bool:
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        payload = {"error": {"message": message, "type": "backend_error"}}
        return _safe_write(
            handler.wfile,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    except Exception as exc:
        if _client_gone(exc):
            log(f"⚠️ CLIENT_DISCONNECTED before error response: {exc}")
            return False
        raise


def _send_kilo_failure(
    handler,
    stream: bool,
    tools: list | None,
    message: str,
    *,
    status: int = 502,
) -> bool:
    """Agent mode: return attempt_completion instead of bare HTTP error when possible."""
    fallback = failure_as_kilo_tool(tools, message)
    if fallback:
        return _send_openai_completion(handler, stream, fallback.content, fallback.tool_calls)
    return _send_provider_error(handler, status, message)


def _send_openai_completion(handler, stream: bool, content: str | None, tool_calls: list) -> bool:
    finish_reason = "tool_calls" if tool_calls else "stop"
    try:
        if stream:
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
            handler.send_header("Cache-Control", "no-cache")
            handler.send_header("Connection", "close")
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            write_openai_sse_stream(handler.wfile, content, tool_calls, finish_reason)
            handler.close_connection = True
            return True

        message = {"role": "assistant", "content": content if content else None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        response = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "grok",
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        return _safe_write(
            handler.wfile,
            json.dumps(response, ensure_ascii=False).encode("utf-8"),
        )
    except Exception as exc:
        if _client_gone(exc):
            log(f"⚠️ CLIENT_DISCONNECTED during completion: {exc}")
            return False
        raise


def _get_acpx_path():
    """Robust way to find acpx (hardcoded user path + PATH lookup)."""
    candidates = [
        r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd",
        "acpx.cmd",
        "acpx",
    ]
    for c in candidates:
        if os.path.exists(c) or shutil.which(c):
            return shutil.which(c) or c
    return "acpx.cmd"  # last resort

ACPX_PATH = _get_acpx_path()


def log(msg: str):
    """Логирует и в консоль (когда видно), и всегда в файл рядом с прокси."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    try:
        with open(PROXY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line)
    except UnicodeEncodeError:
        # Windows cp1251 console / redirected stdout cannot print emoji from log messages
        print(line.encode("ascii", errors="replace").decode("ascii"))


def normalize_message_content(content):
    """OpenAI-compatible clients may send content as a string or as a list of parts."""
    return _normalize_content(content)


def extract_system_prompt(messages):
    """Extract and concatenate all system messages for --append-system-prompt.
    This powers the 'grok SYSTEM:' feature.
    """
    if not messages:
        return None
    parts = []
    for m in messages:
        if m.get("role") == "system":
            c = normalize_message_content(m.get("content"))
            if c:
                parts.append(c)
    joined = "\n\n".join(parts).strip()
    return joined if joined else None


def format_messages_for_prompt(messages, include_system=False):
    """Convert chat messages to the plain text prompt format expected by the grok backend.
    Uses USER:/ASSISTANT:/TOOL RESULT: markers.
    When include_system=False (the split path), system messages are omitted here
    and handled via the separate --append-system-prompt mechanism.
    """
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
                tc_text.append(f"tool call {name} with\n{args}")
            prefix = f"ASSISTANT: {content}\n" if content else "ASSISTANT:\n"
            out.append(prefix + "\n".join(tc_text))
            continue

        if role == "tool":
            out.append(f"TOOL RESULT: {content}")
            continue

        r = role.upper()
        out.append(f"{r}: {content}")
    return "\n\n".join(out).strip()


def build_tools_block(tools):
    """Return the AVAILABLE TOOLS + INSTRUCTIONS section that should live in the system prompt.
    Updated for Kilo Code: exactly one tool call per response (matches the SYSTEM rules
    provided to Kilo Code clients).
    """
    if not tools:
        return ""
    block = "\n\nAVAILABLE TOOLS:\n"
    for tool in tools:
        fn = tool.get("function", tool)
        name = fn.get("name", "unknown")
        desc = fn.get("description", "")
        params = fn.get("parameters", {})
        block += f"\n- {name}: {desc}\n  Parameters: {json.dumps(params, ensure_ascii=False)}\n"
    block += """
INSTRUCTIONS:
When you need to use a tool, respond with:
tool call TOOL_NAME with
arg1 is value1
arg2 is value2

You must use exactly one tool call per assistant response. Do not call zero tools or more than one tool in the same response.
"""
    return block


def build_full_prompt(messages, tools=None):
    """Full prompt builder (includes SYSTEM: inside the text). Used for legacy / fallback paths."""
    sys_text = extract_system_prompt(messages) or ""
    conv = format_messages_for_prompt(messages, include_system=True)
    p = ""
    if sys_text:
        p += f"SYSTEM: {sys_text}\n\n"
    if conv:
        p += conv
    if tools:
        p += build_tools_block(tools)
    return p.strip()


def build_prompt_for_backend(messages, tools=None):
    """The key function for grok SYSTEM support.
    Returns (conv, system_append):
      conv         -> the conversation history without any system text (passed as "prompt")
      system_append-> system content + tools block (passed as "system" and turned into --append-system-prompt)
    """
    sys_text = extract_system_prompt(messages) or ""
    conv = format_messages_for_prompt(messages, include_system=False)

    system_append = sys_text
    if tools:
        tools_block = build_tools_block(tools)
        if system_append:
            system_append = (system_append + "\n\n" + tools_block).strip()
        else:
            system_append = tools_block.strip()

    return conv.strip(), (system_append or "").strip()


def clean_acpx_output(raw: str) -> str:
    """Улучшенная очистка вывода acpx exec grok.
    Возвращает ПОЛНЫЙ полезный текст (не только последнюю строку).
    """
    if not raw:
        return ""

    text = raw

    # Удаляем Error handling notification (многострочные)
    text = re.sub(r'Error handling notification \{[\s\S]*?\}\s*\{[\s\S]*?\}', '', text)

    # Построчно фильтруем известный мусор
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(('[client]', '[thinking]', '[done]')):
            continue
        if stripped.startswith('Error handling notification'):
            continue
        if 'jsonrpc' in stripped and ('method' in stripped or 'Error' in stripped):
            continue
        kept.append(stripped)

    # Также пытаемся вытащить ответ, который идёт сразу после [thinking] строки в сыром выводе
    # (на случай если построчный фильтр что-то пропустил). В реальных выводах часто:
    # [thinking] The user query is: "..."
    # ACTUAL ANSWER HERE
    # [client] ...
    if not kept:
        m = re.search(r'\[thinking\][^\n]*\n([\s\S]*?)(?=\n\[client\]|\n\[done\]|\Z)', raw)
        if m:
            candidate = m.group(1).strip()
            kept = [l.strip() for l in candidate.splitlines() if l.strip() and not l.strip().startswith(('[client]', '[thinking]'))]

    # Финальный хак: если в сыром выводе есть "PROMPT TEXT" сразу за [thinking] описанием — берём следующие непустые строки
    if not kept:
        m2 = re.search(r'\[thinking\][^\n]*\n([^\n]+)\s*\n([^\n[]+)', raw)
        if m2:
            kept = [m2.group(2).strip()]

    cleaned = "\n".join(kept).strip()
    return cleaned


class OpenAIProxyHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'OK')
        elif self.path in ['/v1/models', '/models']:
            response = {
                "object": "list",
                "data": [{
                    "id": "grok",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "grok",
                    "capabilities": {"tools": True}
                }]
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        elif self.path in ['/v1/health', '/health']:
            uptime = round(time.time() - _proxy_started_at, 1)
            payload = {
                "status": "ok",
                "architecture": "synthesis-only",
                "uptime_s": uptime,
                "grok_orchestrator": os.environ.get("GROK_ORCHESTRATOR", "synthesis"),
                "grok_synthesis_timeout_s": int(os.environ.get("GROK_SYNTHESIS_TIMEOUT", "240")),
                "prompt_budget": DEFAULT_MAX_PROMPT_CHARS,
                "grok_output_format": os.environ.get("GROK_OUTPUT_FORMAT", "plain"),
                "grok_mcp_bridge": os.environ.get("GROK_MCP_BRIDGE", "1"),
                "grok_retry_timeout_s": _GROK_RETRY_TIMEOUT_S,
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path in ['/v1/chat/completions', '/chat/completions']:
            turn_key = ""
            stream = False
            tools: list = []
            try:
                length = int(self.headers['Content-Length'])
                body = json.loads(self.rfile.read(length).decode('utf-8', errors='replace'))

                stream = body.get('stream', False)
                messages = body.get('messages', [])
                tools = body.get('tools', [])

                # Optional legacy <task> extraction (some frontends wrap the real ask)
                if messages:
                    last = normalize_message_content(messages[-1].get('content'))
                    task_match = re.search(r'<task>(.*?)</task>', last, re.DOTALL)
                    if task_match:
                        # mutate last message content for prompt building
                        messages[-1] = dict(messages[-1])
                        messages[-1]['content'] = task_match.group(1).strip()

                turn_key = _user_turn_key(messages)
                roles = _message_roles_summary(messages)
                start_time = time.time()
                request_id = f"req-{int(time.time()*1000)}"

                log(
                    f"📥 REQUEST (tools={len(tools)}, roles={roles}, "
                    f"intent={detect_intent(messages, tools)}, "
                    f"orchestrator={synthesis_orchestrator_enabled()}, "
                    f"turn_key={turn_key[:48]!r}, mode=synthesis-only)"
                )

                suppress_reason = _should_suppress_duplicate(messages)
                if suppress_reason:
                    cached = _get_cached_response(turn_key)
                    if cached:
                        clean_response, tool_calls = cached
                        log(f"🔁 DUPLICATE_CACHED ({suppress_reason}, request_id={request_id})")
                        _send_openai_completion(self, stream, clean_response, tool_calls)
                        log(f"📤 RESPONSE_SENT cached total_time={time.time() - start_time:.2f}s")
                        return

                wait_evt = _begin_turn(turn_key)
                if wait_evt is not None:
                    cached = _wait_for_turn(turn_key, wait_evt)
                    if cached:
                        clean_response, tool_calls = cached
                        log(f"🔁 DUPLICATE_CACHED (inflight_wait, request_id={request_id})")
                        _send_openai_completion(self, stream, clean_response, tool_calls)
                        log(f"📤 RESPONSE_SENT cached total_time={time.time() - start_time:.2f}s")
                        return

                def _invoke(prompt, retry=False):
                    return _invoke_synthesis_locked(prompt, retry=retry)

                turn = process_chat_turn(
                    messages,
                    tools or None,
                    log=log,
                    invoke_synthesis=_invoke,
                    request_id=request_id,
                )

                if turn.error_message:
                    _release_turn(turn_key)
                    fallback = failure_as_kilo_tool(tools, turn.error_message)
                    if fallback:
                        _release_turn(turn_key, fallback.content, fallback.tool_calls, cache=False)
                        _send_openai_completion(self, stream, fallback.content, fallback.tool_calls)
                        log(f"📤 RESPONSE_SENT synthesis_failure_tool total_time={time.time() - start_time:.2f}s")
                        return
                    _send_kilo_failure(self, stream, tools, turn.error_message, status=turn.error_status)
                    log(f"📤 RESPONSE_SENT error total_time={time.time() - start_time:.2f}s")
                    return

                _release_turn(
                    turn_key,
                    turn.content,
                    turn.tool_calls,
                    cache=turn.cache,
                )
                _send_openai_completion(self, stream, turn.content, turn.tool_calls)
                log(
                    f"📤 RESPONSE_SENT action={turn.action} "
                    f"tools={len(turn.tool_calls)} total_time={time.time() - start_time:.2f}s"
                )
            except Exception as e:
                log(f"❌ UNHANDLED ERROR in chat handler: {e}")
                try:
                    _release_turn(turn_key)
                    if _client_gone(e):
                        log(f"⚠️ CLIENT_DISCONNECTED in chat handler: {e}")
                    else:
                        _send_kilo_failure(
                            self,
                            stream,
                            tools or None,
                            f"Proxy error: {e}",
                            status=500,
                        )
                except Exception as inner:
                    if not _client_gone(inner):
                        log(f"❌ ERROR while sending failure response: {inner}")
        else:
            self.send_error(404)


def extract_tool_calls(text):
    """Extract tool calls from Grok response formatted as:
    tool call tool_name with
    arg1 is value1
    arg2 is value2
    (also supports JSON values for complex args)

    Enforces Kilo Code rule: at most one tool call is returned per response.
    """
    if not text:
        return []

    tool_calls = []

    pattern = r'tool call\s+(\w+)\s+with\s+(.*?)(?=\n\s*tool call|\n\s*$|$)'

    for match in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
        tool_name = match.group(1)
        args_text = match.group(2)

        args = {}
        arg_pattern = r'(\w+)\s+is\s+(.+?)(?=\n\s*\w+\s+is\s+|\n\s*$|$)'
        for arg_match in re.finditer(arg_pattern, args_text, re.DOTALL):
            key = arg_match.group(1)
            value = arg_match.group(2).strip()
            if value.startswith('{') or value.startswith('['):
                try:
                    value = json.loads(value)
                except:
                    pass
            args[key] = value

        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(args, ensure_ascii=False)
            }
        })

    # Enforce exactly one tool call per response (Kilo Code requirement).
    # The injected INSTRUCTIONS tell the model to emit only one; we still cap it here.
    if len(tool_calls) > 1:
        tool_calls = tool_calls[:1]
    return tool_calls


def _serve_on(host: str, port: int) -> None:
    try:
        server = ThreadingHTTPServer((host, port), OpenAIProxyHandler)
    except OSError as e:
        print(f"  ! bind {host}:{port} failed: {e}")
        return
    print(f"  → listening on http://{host}:{port}/v1")
    server.serve_forever()


if __name__ == '__main__':
    port = int(os.environ.get("GROK_PROXY_PORT", "8080"))
    print("=" * 68)
    print("OpenAI proxy — synthesis-only orchestrator (branch feature/synthesis-only-orchestrator)")
    print("Model: grok | Orchestrator:", os.environ.get("GROK_ORCHESTRATOR", "synthesis"))
    print("  - Mechanical: list_files / read_file (proxy)")
    print("  - Grok: single synthesis call (acpx primary)")
    print("  - System prompt через --append-system-prompt (глобальный флаг)")
    print("  - Полные ответы (без обрезки до последней строки)")
    print("  - Все тайминги и сырой вывод пишутся в proxy_requests.log")
    print("  - Kilo Code: строго один tool call на ответ (см. build_tools_block и extract_tool_calls)")
    print()
    print("Kilo / OpenAI-compatible client:")
    print("  Provider: OpenAI Compatible")
    print("  Base URL: http://127.0.0.1:8080/v1  (prefer over localhost on Windows)")
    print("  API Key : dummy")
    print("  Model   : grok")
    print("=" * 68)

    # Windows Node/Kilo often resolves localhost → ::1 (IPv6); bind both stacks.
    hosts = ["127.0.0.1"]
    if socket.has_ipv6:
        hosts.append("::1")
    if len(hosts) == 1:
        _serve_on(hosts[0], port)
    else:
        threads = []
        for host in hosts:
            t = threading.Thread(target=_serve_on, args=(host, port), daemon=True)
            t.start()
            threads.append(t)
        while True:
            time.sleep(3600)
