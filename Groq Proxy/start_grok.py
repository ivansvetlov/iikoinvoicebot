#!/usr/bin/env python3
"""Start Grok agent + OpenAI proxy.

Use:
  python start_grok.py          # one-shot start (proxy may die after script exits on Windows)
  python start_grok.py --daemon # keeps running, auto-restarts proxy (recommended for Kilo)
  python start_grok.py --visible
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

from paths import log_path

os.chdir(os.path.dirname(__file__))

PROXY_PID_FILE = log_path("proxy.pid")
GROK_PID_FILE = log_path("grok.pid")

# Must live for the whole parent process lifetime (Windows closes inherited handles on exit).
_KEEP_HANDLES: list = []


def write_pid(path, pid):
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(pid))


def read_pid(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def http_ok(url="http://localhost:8080/v1/models", timeout=1.2):
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _win_flags(*, no_window: bool) -> int:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if no_window:
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return flags


def start_grok_agent() -> subprocess.Popen | None:
    if read_pid(GROK_PID_FILE):
        try:
            os.kill(read_pid(GROK_PID_FILE), 0)
            print(f"  → grok agent already running (pid={read_pid(GROK_PID_FILE)})")
            return None
        except OSError:
            pass
    try:
        grok_proc = subprocess.Popen(
            ["grok", "agent", "stdio"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_win_flags(no_window=True),
            close_fds=True,
        )
        write_pid(GROK_PID_FILE, grok_proc.pid)
        print(f"  → grok agent pid={grok_proc.pid}  (saved {GROK_PID_FILE})")
        return grok_proc
    except FileNotFoundError:
        print("  ⚠️  'grok' command not found in PATH.")
    except Exception as e:
        print(f"  ⚠️  Failed to start grok agent: {e}")
    return None


def kill_all_proxy_processes() -> None:
    """Prevent duplicate listeners on :8080 (Windows daemon restarts)."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                'wmic process where "name=\'python.exe\' and CommandLine like \'%openai_proxy%\'" '
                "call terminate >nul 2>&1",
                shell=True,
                check=False,
            )
        except Exception:
            pass
    else:
        pid = read_pid(PROXY_PID_FILE)
        if pid:
            try:
                os.kill(pid, 9)
            except OSError:
                pass


def start_proxy(*, visible: bool = False) -> subprocess.Popen | None:
    kill_all_proxy_processes()
    time.sleep(0.4)
    proxy_cmd = [sys.executable, "-u", "openai_proxy.py"]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault(
        "GROK_DISALLOW_TOOLS",
        "Read,Write,Bash,search_replace,Shell,update_goal,ListDir,Glob,"
        "Grep,Task,WebFetch,WebSearch,NotebookEdit,DeleteFile",
    )
    env.setdefault("GROK_TIMEOUT", "180")
    env.setdefault("GROK_MAX_PROMPT_CHARS", "40000")
    env.setdefault("GROK_MAX_TOOL_RESULT_CHARS", "6000")
    env.setdefault("GROK_RESUME_SESSIONS", "1")
    env.setdefault("GROK_TWO_PHASE", "1")
    env.setdefault("GROK_MCP_BRIDGE", "1")
    env.setdefault("GROK_PASSIVE_CLI", "1")
    env.setdefault("GROK_CLI_PERMISSION", "dontAsk")
    env.setdefault("GROK_RETRY_TIMEOUT_S", "60")
    env["GROK_OUTPUT_FORMAT"] = os.environ.get("GROK_OUTPUT_FORMAT", "json")

    popen_kwargs: dict = {
        "env": env,
        "close_fds": True,
        "creationflags": _win_flags(no_window=not visible),
    }

    if visible:
        popen_kwargs["stdout"] = None
        popen_kwargs["stderr"] = None
    else:
        out = open(log_path("proxy.out.log"), "w", encoding="utf-8", buffering=1)
        err = open(log_path("proxy.err.log"), "w", encoding="utf-8", buffering=1)
        _KEEP_HANDLES[:] = [out, err]
        popen_kwargs["stdout"] = out
        popen_kwargs["stderr"] = err

    try:
        proxy_proc = subprocess.Popen(proxy_cmd, **popen_kwargs)
        write_pid(PROXY_PID_FILE, proxy_proc.pid)
        print(f"  → proxy pid={proxy_proc.pid}  (saved {PROXY_PID_FILE})")
        return proxy_proc
    except Exception as e:
        print(f"  ❌ Failed to start proxy: {e}")
        return None


def wait_ready(seconds: float = 12.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if http_ok():
            return True
        time.sleep(0.8)
    return False


def main():
    visible = "--visible" in sys.argv
    daemon = "--daemon" in sys.argv

    print("Starting Grok ACP agent (grok agent stdio)...")
    start_grok_agent()
    time.sleep(2.2)

    print("Starting OpenAI-compatible proxy on :8080 ...")
    start_proxy(visible=visible)

    print("Waiting for proxy to answer /v1/models ...")
    ready = wait_ready()

    print()
    if ready:
        print("✅ Grok SuperGrok is ready!")
        print("   Base URL: http://localhost:8080/v1  Model: grok  API Key: dummy")
        print("   MCP (parallel): mcp_bridge.py — see mcp_config.example.json")
        print("   Логи: logs/proxy_requests.log")
        if daemon:
            print("   Daemon: watching and auto-restarting proxy")
        else:
            print("   Совет: для Kilo используй  python start_grok.py --daemon")
    else:
        print("⚠️  Proxy not responding. Check logs/proxy.out.log / proxy.err.log")

    if not daemon:
        print("\nUse stop_grok.py to stop.")
        return

    print("\n[daemon] Ctrl+C to stop.")
    last_ok_log = time.time()
    while True:
        time.sleep(10)
        if http_ok("http://localhost:8080/v1/health"):
            if time.time() - last_ok_log >= 600:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] daemon ok — proxy healthy")
                last_ok_log = time.time()
            pid = read_pid(PROXY_PID_FILE)
            if pid:
                try:
                    os.kill(pid, 0)
                except OSError:
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] proxy pid {pid} dead — restarting...")
                    start_proxy(visible=visible)
                    wait_ready(15)
            continue
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] proxy down — restarting...")
        start_proxy(visible=visible)
        wait_ready(15)


if __name__ == "__main__":
    main()
