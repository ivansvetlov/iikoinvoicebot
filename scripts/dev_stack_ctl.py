r"""Fast start/stop/restart for PyCharm dev stack 1/2/5 (+ optional 8 VPN).

Mirrors `.idea/runConfigurations/`:
  1 — uvicorn app.api:app --host 127.0.0.1 --port 8000
  2 — app.entrypoints.worker
  5 — experiments.max_invoice_bot
  8 — scripts/ensure_sotaocr_vpn.ps1

Usage:
  .venv\Scripts\python.exe scripts\dev_stack_ctl.py restart
  .venv\Scripts\python.exe scripts\dev_stack_ctl.py start --only 1,2,5,8
  .venv\Scripts\python.exe scripts\dev_stack_ctl.py stop
  .venv\Scripts\python.exe scripts\dev_stack_ctl.py status
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.subprocess_hidden import hidden_subprocess_kwargs, run_hidden  # noqa: E402

PYTHON = sys.executable
PROJECT_ROOT_LOW = str(PROJECT_ROOT).lower()
SYS_EXE_LOW = (PYTHON or "").lower()
IS_WINDOWS = os.name == "nt"
HEALTH_URL = "http://127.0.0.1:8000/health"
LOG_DIR = PROJECT_ROOT / "logs" / "dev_stack"

# On Windows, prefer pythonw.exe for the stack components so no console window
# pops up for each process (the .cmd wrapper via schtasks would otherwise show
# a cmd.exe window that stays open while the process runs).
if IS_WINDOWS:
    _pythonw = Path(PYTHON).with_name("pythonw.exe")
    STACK_PYTHON = str(_pythonw) if _pythonw.is_file() else PYTHON
else:
    STACK_PYTHON = PYTHON

PYTHON_COMPONENTS = frozenset({"1", "2", "5"})
ALL_COMPONENTS = PYTHON_COMPONENTS | frozenset({"8"})
VPN_SERVICE = "WireGuardTunnel$vpn188958_split_sotaocr"

# Tray monitor lives in the dev-process-monitor worktree (feature branch).
# Launched via its own PS launcher which uses schtasks + pythonw (no window).
TRAY_WORKTREE = PROJECT_ROOT / ".worktrees" / "dev-process-monitor"
TRAY_LAUNCHER = TRAY_WORKTREE / "scripts" / "run_dev_process_monitor.ps1"

COMPONENTS: dict[str, tuple[str, ...]] = {
    "1": ("app.api:app",),
    "2": (
        "app\\entrypoints\\worker.py",
        "app/entrypoints/worker.py",
        "app.entrypoints.worker",
    ),
    "5": (
        "experiments.max_invoice_bot",
        "experiments\\max_invoice_bot",
    ),
}

START_CMDS: dict[str, list[str]] = {
    "1": [STACK_PYTHON, "-m", "uvicorn", "app.api:app", "--host", "127.0.0.1", "--port", "8000"],
    "2": [STACK_PYTHON, "-m", "app.entrypoints.worker"],
    "5": [STACK_PYTHON, "-m", "experiments.max_invoice_bot"],
}


def _list_python_processes() -> list[dict[str, Any]]:
    if not IS_WINDOWS:
        return []
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('python.exe','pythonw.exe') } | "
        "Select-Object ProcessId,CommandLine,ExecutablePath | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw = run_hidden(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            timeout=20,
            text=True,
        ).stdout.strip()
    except Exception:
        return []
    if not raw or raw == "null":
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return [data] if isinstance(data, dict) else data


def _is_project_interpreter(exe_path: str) -> bool:
    exe_low = (exe_path or "").lower()
    if not exe_low:
        return False
    if SYS_EXE_LOW and exe_low == SYS_EXE_LOW:
        return True
    return exe_low.startswith(PROJECT_ROOT_LOW)


def _cmdline_has_project(cmdline: str) -> bool:
    cmd = (cmdline or "").lower()
    return PROJECT_ROOT_LOW in cmd or "pycharmprojects\\pythonproject" in cmd


def _matches_markers(cmdline: str, markers: tuple[str, ...]) -> bool:
    cmd = (cmdline or "").lower()
    return any(marker.lower() in cmd for marker in markers)


def _find_pids(components: set[str]) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {key: [] for key in components}
    for proc in _list_python_processes():
        cmdline = proc.get("CommandLine") or ""
        exe_path = proc.get("ExecutablePath") or ""
        if not _is_project_interpreter(exe_path) and not _cmdline_has_project(cmdline):
            continue
        try:
            pid = int(proc.get("ProcessId"))
        except (TypeError, ValueError):
            continue
        for key in components:
            if _matches_markers(cmdline, COMPONENTS[key]):
                found[key].append(pid)
    return found


def _taskkill(pids: list[int]) -> None:
    if not pids:
        return
    unique = sorted(set(pids))
    if IS_WINDOWS:
        for pid in unique:
            run_hidden(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
            )
        return
    for pid in unique:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def _health_ok() -> bool:
    try:
        resp = httpx.get(HEALTH_URL, timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


def _wait_backend(timeout_sec: float = 12.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _health_ok():
            return True
        time.sleep(0.4)
    return False


def _vpn_ok() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        raw = run_hidden(["sc", "query", VPN_SERVICE], timeout=10).stdout
    except Exception:
        return False
    text = raw.decode("cp866", errors="replace")
    return "RUNNING" in text.upper()


def _start_vpn() -> int:
    script = PROJECT_ROOT / "scripts" / "ensure_sotaocr_vpn.ps1"
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(PROJECT_ROOT),
        timeout=120,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    return proc.returncode


def _tray_running() -> list[int]:
    """Return PIDs of the tray monitor (pythonw running dev_process_monitor)."""
    if not IS_WINDOWS:
        return []
    ps = (
        "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -like '*dev_process_monitor*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        raw = run_hidden(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            timeout=15,
            text=True,
        ).stdout.strip()
    except Exception:
        return []
    if not raw:
        return []
    return [int(x) for x in raw.splitlines() if x.strip().isdigit()]


def _start_tray() -> int:
    """Launch the tray monitor via its worktree PS launcher (no window)."""
    if not IS_WINDOWS:
        return 0
    if not TRAY_LAUNCHER.is_file():
        print("[dev_stack_ctl] tray launcher missing: "
              f"{TRAY_LAUNCHER.relative_to(PROJECT_ROOT)} (worktree absent)")
        return 1
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(TRAY_LAUNCHER),
        ],
        cwd=str(TRAY_WORKTREE),
        capture_output=True,
        timeout=60,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        print(f"[dev_stack_ctl] tray launch failed: {err}", file=sys.stderr)
        return 1
    # Give the launcher a moment to register the process.
    time.sleep(1.0)
    pids = _tray_running()
    if pids:
        print(f"[dev_stack_ctl] tray monitor up PID {pids[0]}")
        return 0
    print("[dev_stack_ctl] tray launcher returned OK but process not detected")
    return 1


def _stop_tray() -> None:
    pids = _tray_running()
    if not pids:
        return
    print(f"[dev_stack_ctl] stop tray: {pids}")
    _taskkill(pids)
    time.sleep(0.3)


def _schtask_name(key: str) -> str:
    return f"PythonProject_devstack_{key}"


def _run_via_schtasks(key: str, bat_path: Path) -> bool:
    task = _schtask_name(key)
    create = subprocess.run(
        [
            "schtasks",
            "/create",
            "/tn",
            task,
            "/tr",
            str(bat_path),
            "/sc",
            "once",
            "/st",
            "23:59",
            "/sd",
            "01/01/2026",
            "/f",
        ],
        capture_output=True,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if create.returncode != 0:
        err = create.stderr.decode("cp866", errors="replace")
        print(f"[dev_stack_ctl] schtasks create failed for {key}: {err}", file=sys.stderr)
        return False
    run = subprocess.run(
        ["schtasks", "/run", "/tn", task],
        capture_output=True,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    if run.returncode != 0:
        err = run.stderr.decode("cp866", errors="replace")
        print(f"[dev_stack_ctl] schtasks run failed for {key}: {err}", file=sys.stderr)
        return False
    return True


def _start_detached(key: str) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{key}.log"
    if IS_WINDOWS:
        cmd_line = subprocess.list2cmdline(START_CMDS[key])
        bat_path = LOG_DIR / f"start_{key}.cmd"
        bat_path.write_text(
            f"@echo off\r\n"
            f'cd /d "{PROJECT_ROOT}"\r\n'
            f"set PYTHONUNBUFFERED=1\r\n"
            f'{cmd_line} >> "{log_path}" 2>&1\r\n',
            encoding="utf-8",
        )
        # Agent shells use job objects: direct Popen/start /B children die when ctl exits.
        # schtasks /run launches outside the job and survives (verified on Windows 10).
        if not _run_via_schtasks(key, bat_path):
            return -1
        print(
            f"[dev_stack_ctl] started {key} via schtasks "
            f"log={log_path.relative_to(PROJECT_ROOT)}"
        )
        return 0
    log_file = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        START_CMDS[key],
        cwd=str(PROJECT_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=True,
    )
    log_file.close()
    print(
        f"[dev_stack_ctl] started {key}: PID {proc.pid} "
        f"log={log_path.relative_to(PROJECT_ROOT)}"
    )
    return proc.pid


def stop(components: set[str]) -> None:
    py_components = components & set(COMPONENTS)
    pids_map = _find_pids(py_components)
    all_pids = [pid for pids in pids_map.values() for pid in pids]
    # Also stop the tray monitor when stopping the Python stack.
    if py_components:
        _stop_tray()
    if not all_pids:
        print("[dev_stack_ctl] stop: nothing running")
        return
    for key, pids in pids_map.items():
        if pids:
            print(f"[dev_stack_ctl] stop {key}: {pids}")
    _taskkill(all_pids)
    time.sleep(0.5)


def start(components: set[str], *, wait_backend: bool = True) -> int:
    exit_code = 0
    if "8" in components:
        if _vpn_ok():
            print("[dev_stack_ctl] VPN already up")
        else:
            rc = _start_vpn()
            if rc != 0 or not _vpn_ok():
                print("[dev_stack_ctl] ERROR: VPN start failed", file=sys.stderr)
                exit_code = 1
            else:
                print("[dev_stack_ctl] VPN OK")

    order = [key for key in ("1", "2", "5") if key in components]
    for key in order:
        if key == "1" and _health_ok():
            print("[dev_stack_ctl] backend already up")
            continue
        running = _find_pids({key})[key]
        if running:
            print(f"[dev_stack_ctl] {key} already running PID {running}")
            continue
        if _start_detached(key) < 0:
            exit_code = 1
            continue
        if key == "1" and wait_backend:
            if _wait_backend(timeout_sec=20.0):
                print("[dev_stack_ctl] backend health OK")
            else:
                print("[dev_stack_ctl] ERROR: backend health timeout", file=sys.stderr)
                exit_code = 1
        elif key in {"2", "5"}:
            time.sleep(1.2)

    # Auto-start the tray monitor whenever the Python stack comes up, so the
    # owner can watch backend/worker/max/vpn state at a glance. Skipped when
    # the caller asked for VPN-only (no 1/2/5).
    started_python = bool(set(COMPONENTS) & set(components))
    if started_python and not _tray_running():
        _start_tray()  # non-fatal if it fails
    return exit_code


def status() -> int:
    pids = _find_pids(set(COMPONENTS))
    lines = ["[dev_stack_ctl] status"]
    ok = True
    for key in ("1", "2", "5"):
        if key == "1":
            health = _health_ok()
            mark = "OK" if health else "—"
            detail = " (health OK)" if health else " (health DOWN)"
            ok = ok and health
        else:
            mark = "OK" if pids[key] else "—"
            detail = f" PID {pids[key]}" if pids[key] else ""
            ok = ok and bool(pids[key])
        lines.append(f"  {key}: {mark}{detail}")
    vpn = _vpn_ok()
    vpn_mark = "OK" if vpn else "—"
    vpn_detail = " (WireGuard split-tunnel)" if vpn else " (DOWN)"
    lines.append(f"  8: {vpn_mark}{vpn_detail}")
    tray_pids = _tray_running()
    tray_mark = "OK" if tray_pids else "—"
    tray_detail = f" PID {tray_pids[0]}" if tray_pids else " (down)"
    lines.append(f"  9: {tray_mark}{tray_detail}  tray monitor")
    print("\n".join(lines))
    return 0 if ok else 1


def restart(components: set[str]) -> int:
    stop(components & set(COMPONENTS))
    return start(components)


def _parse_components(raw: str | None) -> set[str]:
    if not raw:
        return set(PYTHON_COMPONENTS)
    keys = {part.strip() for part in raw.split(",") if part.strip()}
    unknown = keys - set(ALL_COMPONENTS)
    if unknown:
        raise SystemExit(f"Unknown components: {sorted(unknown)}; allowed: 1,2,5,8")
    return keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fast dev stack control (PyCharm 1/2/5/8)")
    parser.add_argument(
        "action",
        choices=("start", "stop", "restart", "status"),
        nargs="?",
        default="restart",
    )
    parser.add_argument(
        "--only",
        dest="only",
        default=None,
        help="comma-separated components: 1,2,5,8 (default: 1,2,5)",
    )
    args = parser.parse_args(argv)
    components = _parse_components(args.only)

    if args.action == "status":
        return status()
    if args.action == "stop":
        stop(components)
        return 0
    if args.action == "start":
        return start(components)
    return restart(components)


if __name__ == "__main__":
    raise SystemExit(main())
