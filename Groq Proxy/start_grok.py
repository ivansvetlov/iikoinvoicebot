#!/usr/bin/env python3
"""Start script for Grok ACP agent + OpenAI proxy.
Creates .pid files so stop can cleanly target only our processes.
"""
import subprocess
import os
import sys
import time
import urllib.request
import urllib.error

from paths import log_path

os.chdir(os.path.dirname(__file__))

PROXY_PID_FILE = log_path("proxy.pid")
GROK_PID_FILE = log_path("grok.pid")


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


print("Starting Grok ACP agent (grok agent stdio)...")
grok_proc = None
try:
    grok_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    grok_proc = subprocess.Popen(
        ["grok", "agent", "stdio"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=grok_flags,
        close_fds=True
    )
    write_pid(GROK_PID_FILE, grok_proc.pid)
    print(f"  → grok agent pid={grok_proc.pid}  (saved {GROK_PID_FILE})")
except FileNotFoundError:
    print("  ⚠️  'grok' command not found in PATH. Make sure the Grok CLI / ACP is installed.")
except Exception as e:
    print(f"  ⚠️  Failed to start grok agent: {e}")

time.sleep(2.2)

print("Starting OpenAI-compatible proxy on :8080 ...")
proxy_proc = None
try:
    visible = "--visible" in sys.argv
    proxy_cmd = [sys.executable, "-u", "openai_proxy.py"]  # -u = unbuffered

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Use DETACHED_PROCESS so the proxy survives after this start script exits (common Windows gotcha)
    base_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if not visible:
        base_flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

    popen_kwargs = {
        "creationflags": base_flags,
        "env": env,
        "close_fds": True,
    }

    if not visible:
        # Логи всегда сохраняются, даже когда окно скрыто
        popen_kwargs["stdout"] = open(log_path("proxy.out.log"), "w", encoding="utf-8")
        popen_kwargs["stderr"] = open(log_path("proxy.err.log"), "w", encoding="utf-8")

    proxy_proc = subprocess.Popen(proxy_cmd, **popen_kwargs)
    write_pid(PROXY_PID_FILE, proxy_proc.pid)
    print(f"  → proxy pid={proxy_proc.pid}  (saved {PROXY_PID_FILE})")
    if not visible:
        print("     (stdout/stderr → logs/proxy.out.log + logs/proxy.err.log + logs/proxy_requests.log)")
except Exception as e:
    print(f"  ❌ Failed to start proxy: {e}")

# readiness probe
print("Waiting for proxy to answer /v1/models ...")
ready = False
for _ in range(15):
    if http_ok():
        ready = True
        break
    time.sleep(0.8)

print()
if ready:
    print("✅ Grok SuperGrok is ready!")
    print("   Kilo Code / Continue.dev config:")
    print("     Provider: OpenAI Compatible")
    print("     Base URL: http://localhost:8080/v1")
    print("     API Key : dummy   (or anything)")
    print("     Model   : grok")
    print("   Логи прокси: logs/proxy_requests.log, logs/proxy.out.log, logs/proxy.err.log")
    print("   Запуск с видимым окном: python start_grok.py --visible")
else:
    print("⚠️  Proxy process started but endpoint not responding yet.")
    print("   Check logs/proxy.out.log / logs/proxy.err.log / logs/proxy_requests.log")

print()
print("Use stop_grok.py (or the GUI manager) to stop.")
