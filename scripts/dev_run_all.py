r"""Start backend, worker and bot for local development.

Usage:
    .venv\Scripts\python.exe scripts\dev_run_all.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


@dataclass
class ProcGroup:
    backend: subprocess.Popen | None = None
    worker: subprocess.Popen | None = None
    bot: subprocess.Popen | None = None

    def terminate_all(self) -> None:
        for name in ("bot", "worker", "backend"):
            proc = getattr(self, name)
            if proc is None:
                continue
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
            except Exception:
                pass


def _get_health(url: str) -> bool:
    try:
        resp = httpx.get(url, timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _kill_duplicate_bot_processes() -> None:
    """Stop other bot polling processes from the same project interpreter."""
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('python.exe','pythonw.exe') } | "
        "Select-Object ProcessId,CommandLine,ExecutablePath,Name | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], text=True)
    except Exception as exc:
        print(f"[dev_run_all] duplicate-bot check failed: {exc.__class__.__name__}: {exc}")
        return

    raw = raw.strip()
    if not raw or raw == "null":
        return

    try:
        data = json.loads(raw)
    except Exception as exc:
        print(f"[dev_run_all] duplicate-bot check failed: invalid JSON ({exc.__class__.__name__})")
        return

    processes = [data] if isinstance(data, dict) else data
    project_root_low = str(PROJECT_ROOT).lower()
    sys_exe_low = (sys.executable or "").lower()

    to_kill: list[int] = []
    for proc in processes:
        try:
            pid = int(proc.get("ProcessId"))
            cmdline = (proc.get("CommandLine") or "")
            exe_path = (proc.get("ExecutablePath") or "")
        except Exception:
            continue

        if pid == os.getpid():
            continue

        cmd_low = cmdline.lower()
        is_bot_script = "bot.py" in cmd_low
        is_bot_module = "app.entrypoints.bot" in cmd_low
        if not (is_bot_script or is_bot_module):
            continue

        exe_low = exe_path.lower()
        is_same_interpreter = bool(sys_exe_low) and exe_low == sys_exe_low
        is_project_venv = exe_low.startswith(project_root_low)
        if not (is_same_interpreter or is_project_venv):
            continue
        to_kill.append(pid)

    if not to_kill:
        return

    print(f"[dev_run_all] found {len(to_kill)} existing bot processes, stopping: {to_kill}")
    for pid in to_kill:
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    for pid in to_kill:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_backend(group: ProcGroup) -> None:
    url = "http://127.0.0.1:8000/health"
    if _get_health(url):
        print(f"[dev_run_all] backend already up ({url}), skipping start")
        return

    cmd = [PYTHON, "-m", "uvicorn", "app.entrypoints.main:app", "--host", "127.0.0.1", "--port", "8000"]
    print("[dev_run_all] starting backend:", " ".join(cmd))
    group.backend = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))

    for attempt in range(10):
        time.sleep(1)
        if _get_health(url):
            print("[dev_run_all] backend is up (", url, ")")
            return
        print(f"[dev_run_all] backend not ready (attempt={attempt + 1}), retry...")
    raise RuntimeError("backend health check failed")


def start_worker(group: ProcGroup) -> None:
    cmd = [PYTHON, "-m", "app.entrypoints.worker"]
    print("[dev_run_all] starting worker:", " ".join(cmd))
    group.worker = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
    time.sleep(1)


def start_bot(group: ProcGroup) -> None:
    _kill_duplicate_bot_processes()
    cmd = [PYTHON, "-m", "app.entrypoints.bot"]
    print("[dev_run_all] starting bot:", " ".join(cmd))
    group.bot = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
    time.sleep(1)


def main() -> None:
    group = ProcGroup()
    try:
        start_backend(group)
        start_worker(group)
        start_bot(group)

        print("\n[dev_run_all] all processes started:")
        if group.backend:
            print(f"  backend PID={group.backend.pid}")
        if group.worker:
            print(f"  worker  PID={group.worker.pid}")
        if group.bot:
            print(f"  bot     PID={group.bot.pid}")
        print("\nPress Ctrl+C to stop all processes.")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[dev_run_all] interrupted by user, terminating...")
    except Exception as exc:
        print(f"[dev_run_all] ERROR: {exc!r}")
    finally:
        group.terminate_all()
        print("[dev_run_all] all processes terminated")


if __name__ == "__main__":
    main()
