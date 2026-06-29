"""Serve project root over HTTP for local dashboard access.

Default: http://0.0.0.0:8765 (LAN + localhost)

  .venv\\Scripts\\python.exe scripts\\serve_project_dashboard.py
"""
from __future__ import annotations

import argparse
import http.server
import os
import socket
import socketserver
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_REL = "docs/assets/project-dashboard.html"


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def _probe_dashboard(port: int) -> bool:
    url = f"http://127.0.0.1:{port}/{DASHBOARD_REL}"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _print_urls(port: int) -> None:
    print(f"Serving {PROJECT_ROOT}")
    print(f"Local:    http://127.0.0.1:{port}/{DASHBOARD_REL}")
    try:
        from experiments.grok_telegram_bridge.dashboard_hub import local_lan_ip, tailscale_ip

        lan = local_lan_ip()
        if lan:
            print(f"Phone/LAN: http://{lan}:{port}/{DASHBOARD_REL}")
        ts = tailscale_ip()
        if ts:
            print(f"Tailscale: http://{ts}:{port}/{DASHBOARD_REL}")
        cf = os.environ.get("CLOUDFLARE_DASHBOARD_URL", "").strip()
        if cf:
            print(f"Cloudflare: {cf}")
    except Exception:
        pass


def _stop_existing_dashboard() -> None:
    ctl = PROJECT_ROOT / "scripts" / "grok_bridge_ctl.py"
    if not ctl.exists():
        return
    import subprocess

    subprocess.run(
        [
            sys.executable,
            str(ctl),
            "dashboard-stop",
            "--exclude-pid",
            str(os.getpid()),
        ],
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    time.sleep(0.6)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve project dashboard files")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="bind address (0.0.0.0 = LAN + localhost)",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--force",
        action="store_true",
        help="stop existing dashboard on this port, then start",
    )
    args = parser.parse_args()

    if args.force:
        _stop_existing_dashboard()
    elif _port_open("127.0.0.1", args.port) and _probe_dashboard(args.port):
        _print_urls(args.port)
        print(
            f"\nDashboard already running on port {args.port}. "
            "Use --force to restart, or grok_bridge_ctl.py dashboard-stop."
        )
        return
    elif _port_open("127.0.0.1", args.port):
        raise SystemExit(
            f"Port {args.port} is in use by another process. "
            "Stop it or run with --force (only stops project dashboard)."
        )

    handler = http.server.SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer((args.host, args.port), handler)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or exc.errno in {48, 98}:
            if _probe_dashboard(args.port):
                _print_urls(args.port)
                print(f"\nDashboard already running on port {args.port}.")
                return
        raise
    with httpd:
        os.chdir(PROJECT_ROOT)
        _print_urls(args.port)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
