"""WireGuard split-tunnel control for the recognition VPN (Windows dev).

Single entrypoint to manage the WireGuard split-tunnel that routes SotaOCR +
api.openai.com through VPN from a Windows dev box. On Linux/VPS this is a
no-op (the tunnel is a deployment concern there).

Usage::

    python scripts/vpn_ctl.py status      # is the tunnel up? which config? routes?
    python scripts/vpn_ctl.py up          # start the tunnel (installs service if needed)
    python scripts/vpn_ctl.py down        # stop the tunnel
    python scripts/vpn_ctl.py restart     # down + up
    python scripts/vpn_ctl.py logs [N]    # last N log lines (default 50)

Config selection::

    The tunnel config is chosen via env ``SOTAOCR_WG_CONFIG`` (absolute or
    project-relative path). Default: ``config/wireguard/vpn188958_split_sotaocr.conf``.
    To switch provider/protocol, point this env at a different ``.conf`` file
    (WireGuard config format is provider-agnostic).

Note::

    The tunnel is an explicit dev component, not tied to the worker lifecycle.
    ``up`` brings it up on demand (self-elevates via UAC if needed, like the
    PowerShell helper); ``down`` stops it (also requires admin rights and will
    self-elevate). The Windows service start mode should be **Manual** so the
    tunnel does not start at OS boot.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ocr.vpn import (  # noqa: E402
    ENSURE_SCRIPT,
    SPLIT_SERVICE,
    ensure_api_vpn,
    is_split_tunnel_running,
    split_config_path,
    stop_tunnel,
)


def _is_windows() -> bool:
    return sys.platform == "win32"


def _config_info() -> dict[str, str]:
    return {
        "service": SPLIT_SERVICE,
        "config": str(split_config_path()),
        "config_exists": "yes" if split_config_path().is_file() else "NO (missing!)",
        "ensure_script": "yes" if ENSURE_SCRIPT.is_file() else "NO (missing!)",
        "env_var": os.environ.get("SOTAOCR_WG_CONFIG", "(not set, using default)"),
    }


def _service_query(field: str) -> str:
    """Query a service property via PowerShell (reliable with '$' in names).

    field: 'Status' or 'StartType'.
    """
    if not _is_windows():
        return "n/a"
    # PowerShell handles the '$' in the service name; sc.exe does not.
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-Service -Name '{SPLIT_SERVICE}' -ErrorAction SilentlyContinue).{field}",
    ]
    try:
        completed = subprocess.run(
            cmd, capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"query failed: {exc}"
    text = completed.stdout.decode("utf-8", errors="replace").strip()
    return text or "service not found"


def _service_state() -> str:
    return _service_query("Status")


def _service_start_type() -> str:
    return _service_query("StartType")


def cmd_status() -> int:
    info = _config_info()
    running = is_split_tunnel_running()
    print("=== Recognition VPN (WireGuard split-tunnel) ===")
    print(f"  Running:     {'YES' if running else 'no'}")
    print(f"  Service:     {info['service']}")
    print(f"  State:       {_service_state()}")
    print(f"  Start type:  {_service_start_type()}  (Manual = does NOT start at boot)")
    print(f"  Config:      {info['config']}")
    print(f"  Config file: {info['config_exists']}")
    print(f"  Env SOTAOCR_WG_CONFIG: {info['env_var']}")
    print(f"  Ensure script: {info['ensure_script']}")
    if not _is_windows():
        print("\n  Non-Windows: VPN is a deployment concern; this CLI is a no-op.")
    return 0


def cmd_up() -> int:
    if not _is_windows():
        print("Non-Windows: nothing to do.")
        return 0
    print("Starting recognition VPN tunnel...")
    if ensure_api_vpn(raise_on_failure=False):
        print("OK: tunnel is up.")
        return 0
    print("FAILED: tunnel did not come up. Check config and WireGuard install.")
    print(f"  Config: {split_config_path()}")
    return 1


def _is_admin() -> bool:
    """True if the current process has administrator rights (Windows)."""
    if not _is_windows():
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _relaunch_elevated(action: str) -> int:
    """Re-launch this script elevated (UAC prompt) to perform `action`.

    Used by `down` and `set-manual` which need admin rights. `up` does not
    need this — `ensure_api_vpn` already self-elevates via the PowerShell
    helper. The elevated process opens in a new window (it cannot inherit
    this console); check the result afterwards with `status`.
    """
    if not _is_windows():
        return 0
    script = str(Path(__file__).resolve())
    # Build the parameter string for the elevated python invocation.
    # ShellExecuteW wants a single string; quote paths with spaces.
    params = f'"{script}" {action}'
    exe = sys.executable
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", exe, params, str(PROJECT_ROOT), 1
    )
    # ShellExecuteW returns > 32 on success.
    if rc <= 32:
        print(f"Elevation declined or failed (rc={rc}). Run '{action}' as administrator manually.")
        return 1
    print(f"Elevated '{action}' launched in a new window. Check result with: vpn_ctl.py status")
    return 0


def cmd_down() -> int:
    if not _is_windows():
        print("Non-Windows: nothing to do.")
        return 0
    if not _is_admin():
        print("Stopping the tunnel requires administrator rights. Requesting elevation...")
        return _relaunch_elevated("down")
    print("Stopping recognition VPN tunnel...")
    if stop_tunnel(timeout=20):
        print("OK: tunnel is down.")
        return 0
    print("FAILED: tunnel did not stop in time.")
    return 1


def cmd_restart() -> int:
    cmd_down()
    return cmd_up()


def cmd_logs(n: int) -> int:
    if not _is_windows():
        print("Non-Windows: no logs.")
        return 0
    # WireGuard service logs via Windows event log; tail via wevtutil/powershell.
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-WinEvent -FilterHashtable @{LogName='Application'; "
            f"ProviderName='WireGuard'}} -MaxEvents {n} -ErrorAction SilentlyContinue | "
            "ForEach-Object { '{0}  {1}' -f $_.TimeCreated, $_.Message }"
        ),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Failed to read logs: {exc}")
        return 1
    text = completed.stdout.decode("utf-8", errors="replace").strip()
    if not text:
        print("(no WireGuard events found)")
    else:
        print(text)
    return 0


def _set_manual_start() -> int:
    """Set the service to Manual start (does not start at OS boot)."""
    if not _is_windows():
        print("Non-Windows: nothing to do.")
        return 0
    if not _is_admin():
        print("Setting service start type requires administrator rights. Requesting elevation...")
        return _relaunch_elevated("set-manual")
    print(f"Setting {SPLIT_SERVICE} to Manual start...")
    # Set-Service handles '$' in the service name reliably; sc.exe does not.
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Set-Service -Name '{SPLIT_SERVICE}' -StartupType Manual",
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Failed: {exc}")
        return 1
    if completed.returncode != 0:
        err = completed.stderr.decode("utf-8", errors="replace").strip()
        print(f"Failed: {err}")
        return 1
    print("OK (Manual). The tunnel will not start at OS boot.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recognition VPN (WireGuard split-tunnel) control."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Show tunnel state, config, routes.")
    sub.add_parser("up", help="Start the tunnel.")
    sub.add_parser("down", help="Stop the tunnel.")
    sub.add_parser("restart", help="Stop then start the tunnel.")
    logs = sub.add_parser("logs", help="Show last N WireGuard event-log lines.")
    logs.add_argument("n", nargs="?", type=int, default=50)
    sub.add_parser("set-manual", help="Set service to Manual start (no boot autostart).")
    args = parser.parse_args()

    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "up":
        return cmd_up()
    if args.cmd == "down":
        return cmd_down()
    if args.cmd == "restart":
        return cmd_restart()
    if args.cmd == "logs":
        return cmd_logs(args.n)
    if args.cmd == "set-manual":
        return _set_manual_start()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
