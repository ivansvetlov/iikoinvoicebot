"""GeoHide DNS + Sing-box status for Windows dev (OpenAI routing).

GeoHide stack (user-provided):
  - AdGuard Home on 53 / 444 / 853 — DNS rewrites blocked domains to GeoHide proxy IPs
  - Sing-box on 80 / 443 — HTTPS proxy to abroad for those domains only
  - Optional static hosts: %SystemRoot%\\System32\\drivers\\etc\\hosts

Set in .env:
  RECOGNITION_ROUTE=geohide

Then stop WireGuard component 8 (conflicts with GeoHide for OpenAI):
  .venv\\Scripts\\python.exe scripts\\vpn_ctl.py down
"""
from __future__ import annotations

import argparse
import ctypes
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ocr.routing import (  # noqa: E402
    GEOHIDE_OPENAI_HOST,
    geohide_openai_ips,
    is_geohide_route_ok,
    is_local_geohide_stack_listening,
    recognition_route,
)
from app.ocr.vpn import is_split_tunnel_running  # noqa: E402

DEFAULT_HOSTS_SRC = Path.home() / "Downloads" / "hosts"
DEFAULT_ADGUARD_SRC = Path.home() / "Downloads" / "GeoHide-AdGuardHome-15-06-2026.txt"
SYSTEM_HOSTS = Path(r"C:\Windows\System32\drivers\etc\hosts")
CONFIG_DIR = PROJECT_ROOT / "config" / "geohide"
ENV_FILE = PROJECT_ROOT / ".env"
HOSTS_REF = CONFIG_DIR / "hosts.geohide"


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_admin() -> bool:
    if not _is_windows():
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _relaunch_elevated(action: str, extra: str = "") -> int:
    script = str(Path(__file__).resolve())
    params = f'"{script}" {action}'
    if extra:
        params = f"{params} {extra}"
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, str(PROJECT_ROOT), 1
    )
    if rc <= 32:
        print(f"Elevation declined or failed (rc={rc}). Run as administrator manually.")
        return 1
    print(f"Elevated '{action}' launched (UAC). Check: geohide_ctl.py status")
    return 0


def _resolve_hosts_src(args_hosts: str | None) -> Path:
    if args_hosts:
        return Path(args_hosts)
    if HOSTS_REF.is_file():
        return HOSTS_REF
    if DEFAULT_HOSTS_SRC.is_file():
        return DEFAULT_HOSTS_SRC
    raise FileNotFoundError(
        f"GeoHide hosts not found. Run install-refs or put file at {DEFAULT_HOSTS_SRC}"
    )


def _flush_dns() -> None:
    if not _is_windows():
        return
    try:
        subprocess.run(["ipconfig", "/flushdns"], check=False, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _print_header(title: str) -> None:
    print(f"=== {title} ===")


def cmd_status(_: argparse.Namespace) -> int:
    _print_header("Recognition routing")
    print(f"  RECOGNITION_ROUTE: {recognition_route()}")
    print(f"  WireGuard running: {'YES' if is_split_tunnel_running() else 'NO'}")
    print(f"  GeoHide DNS ok:    {'YES' if is_geohide_route_ok() else 'NO'}")
    print(f"  Local stack ports: {'YES' if is_local_geohide_stack_listening() else 'NO'}")
    resolved = sorted(geohide_openai_ips())
    print(f"  {GEOHIDE_OPENAI_HOST} -> {', '.join(resolved) or '(no A records)'}")
    if is_split_tunnel_running() and recognition_route() == "geohide":
        print("  WARN: WireGuard and GeoHide both active — prefer one route for OpenAI.")
    return 0


def cmd_install_refs(args: argparse.Namespace) -> int:
    """Copy reference GeoHide files into repo (no admin)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    hosts_src = Path(args.hosts or DEFAULT_HOSTS_SRC)
    adguard_src = Path(args.adguard or DEFAULT_ADGUARD_SRC)
    copied = 0
    for src, name in ((hosts_src, "hosts.geohide"), (adguard_src, "AdGuardHome-geohide.txt")):
        if not src.is_file():
            print(f"  skip (missing): {src}")
            continue
        dest = CONFIG_DIR / name
        shutil.copy2(src, dest)
        print(f"  copied: {dest}")
        copied += 1
    if not copied:
        print("Nothing copied. Put hosts + AdGuard list in Downloads or pass --hosts/--adguard.")
        return 1
    return 0


def cmd_plan(_: argparse.Namespace) -> int:
    _print_header("GeoHide setup (Windows, recommended)")
    print("Fast path (hosts only — proxy runs on GeoHide servers, not locally):")
    print("  .venv\\Scripts\\python.exe scripts\\geohide_ctl.py setup")
    print()
    print("Manual equivalent:")
    print(f"  1. Copy GeoHide hosts -> {SYSTEM_HOSTS} (admin)")
    print("  2. .env: RECOGNITION_ROUTE=geohide")
    print("  3. scripts\\vpn_ctl.py down")
    print("  4. ipconfig /flushdns")
    print("  5. scripts\\dev_stack_ctl.py restart --only 2")
    print()
    print("Advanced (local AdGuard + Sing-box): see plan-full")
    return 0


def cmd_plan_full(_: argparse.Namespace) -> int:
    _print_header("GeoHide full stack (local AdGuard + Sing-box)")
    print("1. AdGuard Home — import:")
    print(f"     {CONFIG_DIR / 'AdGuardHome-geohide.txt'}")
    print("2. Sing-box on 127.0.0.1:80 and :443")
    print("3. Windows DNS -> 127.0.0.1")
    print("4. RECOGNITION_ROUTE=geohide in .env")
    print("5. WireGuard off: vpn_ctl.py down")
    return 0


def cmd_configure_env(_: argparse.Namespace) -> int:
    if not ENV_FILE.is_file():
        print(f"Missing {ENV_FILE}")
        return 1
    text = ENV_FILE.read_text(encoding="utf-8-sig")
    line = "RECOGNITION_ROUTE=geohide"
    if re.search(r"^RECOGNITION_ROUTE=", text, flags=re.MULTILINE):
        text = re.sub(r"^RECOGNITION_ROUTE=.*$", line, text, count=1, flags=re.MULTILINE)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n# GeoHide DNS routing for OpenAI (see scripts/geohide_ctl.py)\n{line}\n"
    ENV_FILE.write_text(text, encoding="utf-8")
    print(f"Updated {ENV_FILE}: {line}")
    return 0


def cmd_install_hosts(args: argparse.Namespace) -> int:
    if not _is_windows():
        print("install-hosts: Windows only")
        return 1
    if not _is_admin():
        print("Installing hosts requires administrator rights. Requesting elevation...")
        extra = f'--hosts "{args.hosts}"' if args.hosts else ""
        return _relaunch_elevated("install-hosts", extra.strip())

    try:
        src = _resolve_hosts_src(args.hosts)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    backup = SYSTEM_HOSTS.with_name(
        f"hosts.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    if SYSTEM_HOSTS.is_file():
        shutil.copy2(SYSTEM_HOSTS, backup)
        print(f"Backup: {backup}")
    shutil.copy2(src, SYSTEM_HOSTS)
    print(f"Installed GeoHide hosts: {src} -> {SYSTEM_HOSTS}")
    _flush_dns()
    print("DNS cache flushed.")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    print("[1/4] Configure .env")
    if cmd_configure_env(argparse.Namespace()) != 0:
        return 1

    print("[2/4] Install GeoHide hosts (UAC if needed)")
    if cmd_install_hosts(argparse.Namespace(hosts=args.hosts)) != 0:
        print("Hosts install pending UAC — after approval, run: geohide_ctl.py finish-setup")
        return 0

    return cmd_finish_setup(argparse.Namespace(skip_hosts=True))


def cmd_finish_setup(args: argparse.Namespace) -> int:
    if not args.skip_hosts and not is_geohide_route_ok():
        print("GeoHide hosts not active yet. Run: geohide_ctl.py install-hosts")
        return 1

    print("[3/4] Stop WireGuard split-tunnel")
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "vpn_ctl.py"), "down"],
        cwd=str(PROJECT_ROOT),
        check=False,
    )

    _flush_dns()
    print("[4/4] Verify routing")
    rc = cmd_status(argparse.Namespace())

    if is_geohide_route_ok():
        print("\n[OK] GeoHide active. Restart worker:")
        print("  .venv\\Scripts\\python.exe scripts\\dev_stack_ctl.py restart --only 2")
    else:
        print("\n[WARN] api.openai.com still not on GeoHide IPs. Approve UAC or run install-hosts.")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="GeoHide routing helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show GeoHide / WireGuard routing state")
    p_status.set_defaults(func=cmd_status)

    p_refs = sub.add_parser("install-refs", help="Copy GeoHide reference files into config/geohide/")
    p_refs.add_argument("--hosts", help="Path to GeoHide hosts file")
    p_refs.add_argument("--adguard", help="Path to AdGuard Home import list")
    p_refs.set_defaults(func=cmd_install_refs)

    p_plan = sub.add_parser("plan", help="Print setup checklist (hosts path)")
    p_plan.set_defaults(func=cmd_plan)

    p_plan_full = sub.add_parser("plan-full", help="Print local AdGuard+Sing-box checklist")
    p_plan_full.set_defaults(func=cmd_plan_full)

    p_env = sub.add_parser("configure-env", help="Set RECOGNITION_ROUTE=geohide in .env")
    p_env.set_defaults(func=cmd_configure_env)

    p_hosts = sub.add_parser("install-hosts", help="Install GeoHide hosts file (admin)")
    p_hosts.add_argument("--hosts", help="Source hosts file")
    p_hosts.set_defaults(func=cmd_install_hosts)

    p_setup = sub.add_parser("setup", help="Full setup: .env + hosts + stop WireGuard")
    p_setup.add_argument("--hosts", help="Source hosts file")
    p_setup.set_defaults(func=cmd_setup)

    p_finish = sub.add_parser("finish-setup", help="After UAC hosts install: stop WG and verify")
    p_finish.add_argument("--skip-hosts", action="store_true")
    p_finish.set_defaults(func=cmd_finish_setup)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())