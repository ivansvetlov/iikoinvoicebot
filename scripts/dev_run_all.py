r"""Запуск backend, worker и бота одной командой (для локальной разработки).

Запуск:
    .venv\Scripts\python.exe scripts\dev_run_all.py

Скрипт:
- запускает backend (uvicorn app.api:app --host 127.0.0.1 --port 8000);
- ждёт, пока /health начнёт отвечать;
- запускает worker (`app/entrypoints/worker.py`);
- запускает bot (`app/entrypoints/bot.py`);
- если на любом шаге ошибка — останавливает уже запущенные процессы и
  печатает понятное сообщение.

Доп. защита:
- перед запуском `app/entrypoints/bot.py` пытается найти и остановить **другие**
  процессы бота этого проекта, чтобы не ловить TelegramConflictError.

Это НЕ прод-оркестратор, а удобный помощник для локальной отладки.
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

# Важно: не добавляем сторонних зависимостей ради dev-скрипта. Всё делаем через
# стандартные средства Windows (PowerShell/TaskKill) + Python stdlib.

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PROJECT_ROOT_LOW = str(PROJECT_ROOT).lower()


def _is_project_runtime_process(command_line: str) -> bool:
    cmd = (command_line or "").lower()
    if "pycharmprojects\\pythonproject" not in cmd and PROJECT_ROOT_LOW not in cmd:
        return False
    markers = (
        "app.api:app",
        "app\\entrypoints\\worker.py",
        "app/entrypoints/worker.py",
        "app.entrypoints.worker",
        "app\\entrypoints\\bot.py",
        "app/entrypoints/bot.py",
        "app.entrypoints.bot",
    )
    return any(marker in cmd for marker in markers)


def _kill_existing_project_processes() -> None:
    """Убивает запущенные процессы проекта перед новым стартом (pre-kill)."""
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('python.exe','pythonw.exe') } | "
        "Select-Object ProcessId,ParentProcessId,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], text=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[dev_run_all] pre-kill scan failed: {exc.__class__.__name__}: {exc}")
        return

    raw = raw.strip()
    if not raw or raw == "null":
        return
    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[dev_run_all] pre-kill scan invalid JSON: {exc.__class__.__name__}")
        return

    processes = [data] if isinstance(data, dict) else data
    current_pid = os.getpid()
    to_kill: list[int] = []
    for proc in processes:
        try:
            pid = int(proc.get("ProcessId"))
            cmdline = proc.get("CommandLine") or ""
        except Exception:
            continue
        if pid == current_pid:
            continue
        if _is_project_runtime_process(cmdline):
            to_kill.append(pid)

    if not to_kill:
        return

    to_kill = sorted(set(to_kill))
    print(f"[dev_run_all] pre-kill existing project processes: {to_kill}")
    for pid in to_kill:
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    for pid in to_kill:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)


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
                    # Аккуратно посылаем сигнал завершения
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


def _kill_duplicate_bot_processes() -> None:
    """Останавливает другие процессы `app/entrypoints/bot.py` (в том же venv/проекте).

    Почему это нужно:
    - Telegram polling допускает только один процесс на один токен.
    - Если запустить 2 экземпляра бота, получаем `TelegramConflictError`.

    Нюанс Windows:
    - CommandLine процесса часто содержит только `bot.py` (без cwd/абсолютного пути).
      Поэтому фильтр вида "PROJECT_ROOT in CommandLine" ненадёжен.

    Поэтому считаем процесс «нашим», если:
    - в CommandLine есть `bot.py` (включая `app/entrypoints/bot.py`)
    - и ExecutablePath совпадает с текущим интерпретатором (sys.executable)
      или лежит внутри PROJECT_ROOT (обычно это `.venv\\Scripts\\python.exe`).

    Дополнительно учитываем `pythonw.exe`.

    Реализация через PowerShell (Get-CimInstance), чтобы не добавлять зависимости.
    """

    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('python.exe','pythonw.exe') } | "
        "Select-Object ProcessId,CommandLine,ExecutablePath,Name | "
        "ConvertTo-Json -Compress"
    )

    try:
        raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], text=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[dev_run_all] duplicate-bot check failed: {exc.__class__.__name__}: {exc}")
        return

    raw = raw.strip()
    if not raw or raw == "null":
        return

    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
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
        if "bot.py" not in cmd_low:
            continue

        exe_low = exe_path.lower()

        # 1) Самый надёжный критерий: тот же python.exe (обычно тот же venv)
        is_same_interpreter = bool(sys_exe_low) and exe_low == sys_exe_low

        # 2) Второй критерий: python.exe лежит внутри папки проекта
        # (типично: ...\PythonProject\.venv\Scripts\python.exe)
        is_project_venv = exe_low.startswith(project_root_low)

        if not (is_same_interpreter or is_project_venv):
            continue

        to_kill.append(pid)

    if not to_kill:
        return

    print(f"[dev_run_all] found {len(to_kill)} existing bot processes, stopping: {to_kill}")
    for pid in to_kill:
        # Сначала пробуем мягко
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    for pid in to_kill:
        # Если не остановился — форсим
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_backend(group: ProcGroup) -> None:
    url = "http://127.0.0.1:8000/health"

    # Если backend уже поднят (например, запущен вручную) — используем его.
    if _get_health(url):
        print(f"[dev_run_all] backend already up ({url}), skipping start")
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

    # ждём, пока /health станет доступен
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
    _kill_existing_project_processes()
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

        print("\nНажмите Ctrl+C, чтобы остановить все процессы.")

        # Ожидаем, пока не прервут Ctrl+C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[dev_run_all] interrupted by user, terminating...")
    except Exception as exc:  # noqa: BLE001
        print(f"[dev_run_all] ERROR: {exc!r}")
    finally:
        group.terminate_all()
        print("[dev_run_all] all processes terminated")


if __name__ == "__main__":  # pragma: no cover
    main()
