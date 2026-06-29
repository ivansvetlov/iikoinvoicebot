"""Start/stop/restart Grok bridge processes without touching invoice bot stack.

Scoped to ``experiments.grok_max_bridge`` or ``experiments.grok_telegram_bridge`` only.
Does NOT kill dev_run_all, uvicorn, RQ worker, or app.entrypoints.bot.
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DASHBOARD_PORT = 8765
DASHBOARD_SCRIPT = PROJECT_ROOT / "scripts" / "serve_project_dashboard.py"
DASHBOARD_LOG = PROJECT_ROOT / "logs" / "dashboard_serve.log"
DASHBOARD_LOCK_NAME = "dashboard_serve.lock"

BRIDGE_SPECS: dict[str, dict[str, str]] = {
    "max": {
        "module": "experiments.grok_max_bridge",
        "lock_name": "grok_max_bridge.lock",
        "log_name": "grok_max_bridge.log",
    },
    "telegram": {
        "module": "experiments.grok_telegram_bridge",
        "lock_name": "grok_telegram_bridge.lock",
        "log_name": "grok_telegram_bridge.log",
    },
}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_pids_gone(pids: list[int], *, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(_pid_alive(pid) for pid in pids):
            return
        time.sleep(0.25)


def _python_processes() -> list[dict[str, Any]]:
    """Only python.exe/pythonw.exe — filtered WMI (fast vs full process scan)."""
    if not IS_WINDOWS:
        return []
    ps = (
        "Get-CimInstance Win32_Process -Filter "
        "\"Name='python.exe' OR Name='pythonw.exe'\" | "
        "Select-Object ProcessId,CommandLine,ExecutablePath | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=15,
        ).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[grok_bridge_ctl] process scan failed: {exc.__class__.__name__}", flush=True)
        return []
    if not raw or raw == "null":
        return []
    data = json.loads(raw)
    return [data] if isinstance(data, dict) else list(data)


def _cmdline_for_pid(pid: int) -> str:
    if pid <= 0 or not IS_WINDOWS:
        return ""
    ps = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"
    try:
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return ""


def _matches_marker(cmdline: str, marker: str) -> bool:
    return marker.lower() in (cmdline or "").lower()


def _bridge_pids(module_marker: str) -> list[int]:
    root = str(PROJECT_ROOT).lower()
    pids: list[int] = []
    for proc in _python_processes():
        try:
            pid = int(proc.get("ProcessId"))
            cmd = (proc.get("CommandLine") or "").lower()
            exe = (proc.get("ExecutablePath") or "").lower()
        except Exception:
            continue
        if root not in cmd and root not in exe:
            continue
        if not _matches_marker(cmd, module_marker):
            continue
        if "grok_bridge_ctl.py" in cmd:
            continue
        pids.append(pid)
    return sorted(set(pids))


def _lock_path(name: str) -> Path:
    return PROJECT_ROOT / "tmp" / name


def _read_lock(lock_file: Path) -> int | None:
    if not lock_file.exists():
        return None
    try:
        return int(lock_file.read_text(encoding="utf-8").splitlines()[0].strip())
    except Exception:
        return None


def _write_lock(lock_file: Path, pid: int) -> None:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(f"{pid}\n", encoding="utf-8")


def _clear_lock(lock_file: Path) -> None:
    if lock_file.exists():
        lock_file.unlink()


def _dashboard_pids() -> list[int]:
    marker = "serve_project_dashboard"
    root = str(PROJECT_ROOT).lower()
    pids: list[int] = []
    for proc in _python_processes():
        try:
            pid = int(proc.get("ProcessId"))
            cmd = (proc.get("CommandLine") or "").lower()
            exe = (proc.get("ExecutablePath") or "").lower()
        except Exception:
            continue
        if root not in cmd and root not in exe:
            continue
        if marker not in cmd:
            continue
        pids.append(pid)
    return sorted(set(pids))


def _spawn_detached(cmd: list[str], log_path: Path, *, env: dict[str, str] | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    err_path = log_path.with_suffix(".err.log")
    with log_path.open("a", encoding="utf-8") as out, err_path.open("a", encoding="utf-8") as err:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env or os.environ.copy(),
            stdout=out,
            stderr=err,
            creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
    return proc.pid


def _taskkill(pids: list[int], label: str) -> None:
    unique = sorted({pid for pid in pids if pid > 0})
    if not unique:
        print(f"[grok_bridge_ctl] {label}: nothing to stop", flush=True)
        return
    print(f"[grok_bridge_ctl] {label}: stopping {unique}", flush=True)
    for pid in unique:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[grok_bridge_ctl] taskkill PID={pid} failed: {exc.__class__.__name__}", flush=True)
    _wait_pids_gone(unique)


def _ensure_dashboard_server(python: Path) -> int | None:
    """One dashboard on :8765 — lock + dedupe orphans."""
    dash_lock = _lock_path(DASHBOARD_LOCK_NAME)
    lock_pid = _read_lock(dash_lock)
    if lock_pid and _pid_alive(lock_pid) and _matches_marker(_cmdline_for_pid(lock_pid), "serve_project_dashboard"):
        return lock_pid

    pids = _dashboard_pids()
    if pids:
        keep = pids[-1]
        _write_lock(dash_lock, keep)
        extras = [pid for pid in pids if pid != keep]
        if extras:
            _taskkill(extras, "duplicate dashboard")
        return keep

    if not DASHBOARD_SCRIPT.exists():
        print("[grok_bridge_ctl] dashboard script missing — skip", flush=True)
        return None

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    pid = _spawn_detached(
        [str(python), str(DASHBOARD_SCRIPT), "--host", "0.0.0.0", "--port", str(DASHBOARD_PORT)],
        DASHBOARD_LOG,
        env=env,
    )
    _write_lock(dash_lock, pid)
    print(f"[grok_bridge_ctl] dashboard server PID={pid} port={DASHBOARD_PORT}", flush=True)
    return pid


def cmd_status(bridge: str) -> int:
    spec = BRIDGE_SPECS[bridge]
    lock_file = _lock_path(spec["lock_name"])
    lock_pid = _read_lock(lock_file)
    pids = _bridge_pids(spec["module"])
    print(f"[grok_bridge_ctl] bridge={bridge}", flush=True)
    print(f"  lock: {lock_file} -> {lock_pid}", flush=True)
    print(f"  processes: {pids or '(none)'}", flush=True)
    dash = _dashboard_pids()
    print(f"  dashboard: port {DASHBOARD_PORT} -> {dash or '(not running)'}", flush=True)
    if lock_pid and lock_pid in pids and _pid_alive(lock_pid):
        print("  state: running", flush=True)
        return 0
    if pids:
        _write_lock(lock_file, pids[-1])
        print("  state: running (lock refreshed)", flush=True)
        return 0
    print("  state: stopped", flush=True)
    return 1


def cmd_stop(bridge: str) -> int:
    spec = BRIDGE_SPECS[bridge]
    lock_file = _lock_path(spec["lock_name"])
    pids = _bridge_pids(spec["module"])
    lock_pid = _read_lock(lock_file)
    if lock_pid and lock_pid not in pids and _pid_alive(lock_pid):
        pids.append(lock_pid)
    _taskkill(pids, f"stop {bridge}")
    _clear_lock(lock_file)
    return 0


def cmd_start(bridge: str, *, foreground: bool) -> int:
    spec = BRIDGE_SPECS[bridge]
    lock_file = _lock_path(spec["lock_name"])
    existing = _bridge_pids(spec["module"])
    if existing:
        keep = existing[-1]
        _write_lock(lock_file, keep)
        extras = [pid for pid in existing if pid != keep]
        if extras:
            _taskkill(extras, f"duplicate {bridge}")
        print(f"[grok_bridge_ctl] already running: [{keep}]", flush=True)
        _ensure_dashboard_server(_python_exe())
        return 0

    python = _python_exe()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    module = spec["module"]
    log_path = PROJECT_ROOT / "logs" / spec["log_name"]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if foreground:
        proc = subprocess.Popen([str(python), "-m", module], cwd=str(PROJECT_ROOT), env=env)
        _write_lock(lock_file, proc.pid)
        print(f"[grok_bridge_ctl] started foreground PID={proc.pid}", flush=True)
        return proc.wait()

    pid = _spawn_detached([str(python), "-u", "-m", module], log_path, env=env)
    _write_lock(lock_file, pid)
    print(f"[grok_bridge_ctl] started PID={pid} log={log_path}", flush=True)
    time.sleep(1.5)
    if not _pid_alive(pid):
        print("[grok_bridge_ctl] process exited immediately — check log", flush=True)
        _clear_lock(lock_file)
        return 1
    _ensure_dashboard_server(python)
    return 0


def _python_exe() -> Path:
    python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return python if python.exists() else Path(sys.executable)


def cmd_dashboard_stop(*, exclude_pid: int | None = None) -> int:
    dash_lock = _lock_path(DASHBOARD_LOCK_NAME)
    pids = [pid for pid in _dashboard_pids() if pid != exclude_pid]
    lock_pid = _read_lock(dash_lock)
    if lock_pid and lock_pid not in pids and lock_pid != exclude_pid and _pid_alive(lock_pid):
        pids.append(lock_pid)
    _taskkill(pids, "dashboard")
    _clear_lock(dash_lock)
    return 0


def cmd_restart(bridge: str) -> int:
    cmd_stop(bridge)
    time.sleep(1)
    return cmd_start(bridge, foreground=False)


def cmd_run(bridge: str) -> int:
    """Foreground run for PyCharm: dashboard (bg) + bridge (blocking)."""
    python = _python_exe()
    _ensure_dashboard_server(python)
    spec = BRIDGE_SPECS[bridge]
    lock_file = _lock_path(spec["lock_name"])
    existing = _bridge_pids(spec["module"])
    if existing:
        _taskkill(existing, f"run {bridge}")
    _clear_lock(lock_file)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    print(f"[grok_bridge_ctl] run foreground: {spec['module']}", flush=True)
    proc = subprocess.Popen(
        [str(python), "-m", spec["module"]],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    _write_lock(lock_file, proc.pid)
    try:
        return proc.wait()
    finally:
        _clear_lock(lock_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Grok bridge process control (isolated)")
    parser.add_argument("action", choices=("start", "stop", "restart", "status", "run", "dashboard-stop"))
    parser.add_argument("--bridge", choices=tuple(BRIDGE_SPECS), default="max")
    parser.add_argument("--foreground", action="store_true", help="start in foreground (start only)")
    parser.add_argument("--exclude-pid", type=int, default=None, help="dashboard-stop: keep this PID")
    args = parser.parse_args()

    if args.action == "dashboard-stop":
        return cmd_dashboard_stop(exclude_pid=args.exclude_pid)
    if args.action == "status":
        return cmd_status(args.bridge)
    if args.action == "stop":
        return cmd_stop(args.bridge)
    if args.action == "start":
        return cmd_start(args.bridge, foreground=args.foreground)
    if args.action == "run":
        return cmd_run(args.bridge)
    return cmd_restart(args.bridge)


if __name__ == "__main__":
    raise SystemExit(main())
