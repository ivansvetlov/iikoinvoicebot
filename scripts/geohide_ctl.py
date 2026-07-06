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
import shutil
import sys
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
    _print_header("GeoHide setup (manual, once)")
    print("1. Install AdGuard Home; import DNS list:")
    print(f"     {DEFAULT_ADGUARD_SRC}")
    print("   Or copy from config/geohide/ after: geohide_ctl.py install-refs")
    print("2. Install Sing-box; enable proxy on 127.0.0.1:443 (and :80 if needed).")
    print("3. Windows DNS -> 127.0.0.1 (AdGuard listens on 53).")
    print("4. Optional fallback: replace system hosts (admin):")
    print(f"     copy {DEFAULT_HOSTS_SRC} -> {SYSTEM_HOSTS}")
    print("5. In .env: RECOGNITION_ROUTE=geohide")
    print("6. Stop WireGuard: scripts/vpn_ctl.py down")
    print("7. Restart worker: scripts/dev_stack_ctl.py restart --only 2")
    print()
    print("Note: GeoHide hosts cover OpenAI (api.openai.com). sotaocr.com is NOT in the list —")
    print("SotaOCR may still need WireGuard or a custom AdGuard rewrite for sotaocr.com.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GeoHide routing helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Show GeoHide / WireGuard routing state")
    p_status.set_defaults(func=cmd_status)

    p_refs = sub.add_parser("install-refs", help="Copy GeoHide reference files into config/geohide/")
    p_refs.add_argument("--hosts", help="Path to GeoHide hosts file")
    p_refs.add_argument("--adguard", help="Path to AdGuard Home import list")
    p_refs.set_defaults(func=cmd_install_refs)

    p_plan = sub.add_parser("plan", help="Print setup checklist")
    p_plan.set_defaults(func=cmd_plan)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())