#!/usr/bin/env python3
"""Stop script for the Grok proxy setup.
Prefers .pid files created by start_grok.py for precise kills.
Falls back to targeted name-based cleanup (never kills *all* python.exe).

После остановки можно безопасно запускать заново через start_grok.py.
Логи (proxy_requests.log и т.д.) остаются для анализа.
"""
import subprocess
import os
import time

from paths import log_path

os.chdir(os.path.dirname(__file__))

PROXY_PID_FILE = log_path("proxy.pid")
GROK_PID_FILE = log_path("grok.pid")


def read_pid(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def kill_pid(pid, label="process"):
    if pid is None:
        return False
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"  ✓ killed {label} (pid {pid})")
        return True
    except Exception as e:
        print(f"  ! failed to kill pid {pid}: {e}")
        return False


def safe_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


print("Stopping Grok components...")

proxy_pid = read_pid(PROXY_PID_FILE)
grok_pid = read_pid(GROK_PID_FILE)

killed_any = False

if proxy_pid:
    killed_any |= kill_pid(proxy_pid, "openai-proxy")
safe_remove(PROXY_PID_FILE)

if grok_pid:
    killed_any |= kill_pid(grok_pid, "grok-agent")
safe_remove(GROK_PID_FILE)

# Targeted fallback (only things that look like our grok stack)
if not killed_any:
    print("  (no/invalid pid files - using name fallback)")
    subprocess.run(["taskkill", "/F", "/IM", "grok.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["taskkill", "/F", "/IM", "grok-*.exe"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Only python processes whose command line mentions our proxy (safer than all python)
    try:
        subprocess.run(
            'wmic process where "name=\'python.exe\' and CommandLine like \'%openai_proxy%\'" call terminate >nul 2>&1',
            shell=True
        )
        subprocess.run(
            'wmic process where "name=\'python.exe\' and CommandLine like \'%mcp_grok_adapter%\'" call terminate >nul 2>&1',
            shell=True,
        )
        subprocess.run(
            'wmic process where "name=\'python.exe\' and CommandLine like \'%mcp_bridge%\'" call terminate >nul 2>&1',
            shell=True
        )
    except Exception:
        pass

time.sleep(0.6)
print("✅ Stopped (best effort).")
print("   If something is still running, use Task Manager to kill remaining grok* or the specific python.")
