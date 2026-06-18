r"""Запуск backend, worker и бота одной командой (для локальной разработки).

Запуск:
    .venv\Scripts\python.exe scripts\dev_run_all.py
    .venv\Scripts\python.exe scripts\dev_run_all.py --force
    .venv\Scripts\python.exe scripts\dev_run_all.py --reuse-backend

Скрипт:
- гарантирует один активный оркестратор (lock + pre-kill);
- по умолчанию поднимает свежий стек backend + worker + bot;
- при ошибке на любом шаге останавливает уже запущенные процессы.

Флаги:
- ``--force`` — заменить уже работающий ``dev_run_all`` (убить старый оркестратор).
- ``--reuse-backend`` — не трогать существующий uvicorn, если ``/health`` отвечает
  (удобно, когда backend запущен отдельно в PyCharm).

Это НЕ прод-оркестратор, а удобный помощник для локальной отладки.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# Важно: не добавляем сторонних зависимостей ради dev-скрипта. Всё делаем через
# стандартные средства Windows (PowerShell/TaskKill) + Python stdlib.

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PROJECT_ROOT_LOW = str(PROJECT_ROOT).lower()
SYS_EXE_LOW = (sys.executable or "").lower()
LOCK_PATH = PROJECT_ROOT / "tmp" / "dev_run_all.lock"
IS_WINDOWS = os.name == "nt"

BACKEND_MARKERS = ("app.api:app",)
WORKER_MARKERS = (
    "app\\entrypoints\\worker.py",
    "app/entrypoints/worker.py",
    "app.entrypoints.worker",
)
BOT_MARKERS = (
    "app\\entrypoints\\bot.py",
    "app/entrypoints/bot.py",
    "app.entrypoints.bot",
)
ORCHESTRATOR_MARKERS = (
    "dev_run_all.py",
    "scripts\\dev_run_all.py",
    "scripts/dev_run_all.py",
)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _list_python_processes() -> list[dict[str, Any]]:
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('python.exe','pythonw.exe') } | "
        "Select-Object ProcessId,ParentProcessId,CommandLine,ExecutablePath,Name | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[dev_run_all] process scan failed: {exc.__class__.__name__}: {exc}", flush=True)
        return []

    raw = raw.strip()
    if not raw or raw == "null":
        return []
    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[dev_run_all] process scan invalid JSON: {exc.__class__.__name__}", flush=True)
        return []

    return [data] if isinstance(data, dict) else data


def _is_project_interpreter(exe_path: str) -> bool:
    exe_low = (exe_path or "").lower()
    if not exe_low:
        return False
    if SYS_EXE_LOW and exe_low == SYS_EXE_LOW:
        return True
    return exe_low.startswith(PROJECT_ROOT_LOW)


def _cmdline_has_project_marker(cmdline: str) -> bool:
    cmd = (cmdline or "").lower()
    return PROJECT_ROOT_LOW in cmd or "pycharmprojects\\pythonproject" in cmd


def _matches_markers(cmdline: str, markers: tuple[str, ...]) -> bool:
    cmd = (cmdline or "").lower()
    return any(marker in cmd for marker in markers)


def _protected_pids(processes: list[dict[str, Any]]) -> set[int]:
    """PID'ы, которые нельзя убивать: self, предки и уже запущенные нами дети."""
    current_pid = os.getpid()
    by_pid: dict[int, int] = {}
    for proc in processes:
        try:
            by_pid[int(proc.get("ProcessId"))] = int(proc.get("ParentProcessId") or 0)
        except Exception:
            continue

    protected = {current_pid}
    parent = by_pid.get(current_pid, 0)
    while parent and parent not in protected:
        protected.add(parent)
        parent = by_pid.get(parent, 0)

    for pid, ppid in by_pid.items():
        if ppid == current_pid:
            protected.add(pid)

    return protected


def _classify_dev_process(cmdline: str, exe_path: str) -> str | None:
    if not _is_project_interpreter(exe_path) and not _cmdline_has_project_marker(cmdline):
        return None
    if _matches_markers(cmdline, ORCHESTRATOR_MARKERS):
        return "orchestrator"
    if _matches_markers(cmdline, BACKEND_MARKERS):
        return "backend"
    if _matches_markers(cmdline, WORKER_MARKERS):
        return "worker"
    if _matches_markers(cmdline, BOT_MARKERS):
        return "bot"
    return None


def _taskkill_tree(pids: list[int], label: str) -> None:
    unique = sorted({pid for pid in pids if pid > 0 and pid != os.getpid()})
    if not unique:
        print(f"[dev_run_all] {label}: nothing to stop", flush=True)
        return

    print(f"[dev_run_all] {label}: stopping {unique}", flush=True)
    for pid in unique:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[dev_run_all] {label}: taskkill PID={pid} failed: {exc.__class__.__name__}", flush=True)
    time.sleep(0.5)


def _kill_all_project_dev_processes(*, reuse_backend: bool) -> None:
    """Pre-kill: backend, worker, bot и другие dev_run_all этого проекта."""
    processes = _list_python_processes()
    protected = _protected_pids(processes)
    to_kill: list[int] = []

    for proc in processes:
        try:
            pid = int(proc.get("ProcessId"))
            cmdline = proc.get("CommandLine") or ""
            exe_path = proc.get("ExecutablePath") or ""
        except Exception:
            continue

        if pid in protected:
            continue

        kind = _classify_dev_process(cmdline, exe_path)
        if kind is None:
            continue
        if reuse_backend and kind == "backend":
            continue
        to_kill.append(pid)

    if not to_kill:
        print("[dev_run_all] pre-kill: no matching project processes found", flush=True)
        return

    _taskkill_tree(to_kill, "pre-kill")


def _read_lock_pid() -> int | None:
    if not LOCK_PATH.exists():
        return None
    try:
        first_line = LOCK_PATH.read_text(encoding="utf-8").splitlines()[0].strip()
        return int(first_line)
    except Exception:
        return None


def _is_project_orchestrator_pid(pid: int) -> bool:
    for proc in _list_python_processes():
        try:
            proc_pid = int(proc.get("ProcessId"))
            cmdline = proc.get("CommandLine") or ""
            exe_path = proc.get("ExecutablePath") or ""
        except Exception:
            continue
        if proc_pid != pid:
            continue
        return _classify_dev_process(cmdline, exe_path) == "orchestrator"
    return False


def _release_instance_lock() -> None:
    if not LOCK_PATH.exists():
        return
    try:
        lock_pid = _read_lock_pid()
    except Exception:
        lock_pid = None
    if lock_pid is None or lock_pid == os.getpid():
        LOCK_PATH.unlink(missing_ok=True)


def _acquire_instance_lock(*, force: bool) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing_pid = _read_lock_pid()

    if existing_pid and existing_pid != os.getpid():
        if _pid_alive(existing_pid) and _is_project_orchestrator_pid(existing_pid):
            if force:
                _taskkill_tree([existing_pid], "replacing orchestrator (--force)")
                _release_instance_lock()
            else:
                print(
                    f"[dev_run_all] already running (PID={existing_pid}). "
                    "Stop it or rerun with --force."
                )
                sys.exit(1)
        else:
            print(f"[dev_run_all] removing stale lock (PID={existing_pid})")
            _release_instance_lock()

    LOCK_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    atexit.register(_release_instance_lock)


def _kill_duplicate_role_processes(role: str, markers: tuple[str, ...]) -> None:
    processes = _list_python_processes()
    to_kill: list[int] = []

    for proc in processes:
        try:
            pid = int(proc.get("ProcessId"))
            cmdline = proc.get("CommandLine") or ""
            exe_path = proc.get("ExecutablePath") or ""
        except Exception:
            continue

        if pid in _protected_pids(processes):
            continue
        if not _is_project_interpreter(exe_path):
            continue
        if not _matches_markers(cmdline, markers):
            continue
        to_kill.append(pid)

    if not to_kill:
        return

    _taskkill_tree(to_kill, f"duplicate {role} cleanup")


@dataclass
class ProcGroup:
    backend: subprocess.Popen | None = None
    worker: subprocess.Popen | None = None
    bot: subprocess.Popen | None = None

    def terminate_all(self) -> None:
        child_pids: list[int] = []
        for name in ("bot", "worker", "backend"):
            proc = getattr(self, name)
            if proc is None:
                continue
            if proc.poll() is None and proc.pid:
                child_pids.append(proc.pid)

        if IS_WINDOWS and child_pids:
            _taskkill_tree(child_pids, "shutdown")
            return

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
    except Exception:  # noqa: BLE001
        return False


def start_backend(group: ProcGroup, *, reuse_backend: bool) -> None:
    url = "http://127.0.0.1:8000/health"

    if reuse_backend and _get_health(url):
        print(f"[dev_run_all] reusing existing backend ({url})")
        return

    cmd = [
        PYTHON,
        "-m",
        "uvicorn",
        "app.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
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
    _kill_duplicate_role_processes("worker", WORKER_MARKERS)
    cmd = [PYTHON, "-m", "app.entrypoints.worker"]
    print("[dev_run_all] starting worker:", " ".join(cmd))
    group.worker = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
    time.sleep(1)


def start_bot(group: ProcGroup) -> None:
    _kill_duplicate_role_processes("bot", BOT_MARKERS)
    cmd = [PYTHON, "-m", "app.entrypoints.bot"]
    print("[dev_run_all] starting bot:", " ".join(cmd))
    group.bot = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
    time.sleep(1)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local dev orchestrator: backend + worker + bot")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an already running dev_run_all instance",
    )
    parser.add_argument(
        "--reuse-backend",
        action="store_true",
        help="keep existing uvicorn when /health already responds",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    _acquire_instance_lock(force=args.force)
    _kill_all_project_dev_processes(reuse_backend=args.reuse_backend)

    group = ProcGroup()
    try:
        start_backend(group, reuse_backend=args.reuse_backend)
        start_worker(group)
        start_bot(group)

        print("\n[dev_run_all] all processes started:")
        if group.backend:
            print(f"  backend PID={group.backend.pid}")
        else:
            print("  backend PID=(reused existing)")
        if group.worker:
            print(f"  worker  PID={group.worker.pid}")
        if group.bot:
            print(f"  bot     PID={group.bot.pid}")

        print("\nНажмите Ctrl+C, чтобы остановить все процессы.")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[dev_run_all] interrupted by user, terminating...")
    except Exception as exc:  # noqa: BLE001
        print(f"[dev_run_all] ERROR: {exc!r}")
    finally:
        group.terminate_all()
        _release_instance_lock()
        print("[dev_run_all] all processes terminated")


if __name__ == "__main__":  # pragma: no cover
    main()
