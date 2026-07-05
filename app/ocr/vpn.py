"""WireGuard split-tunnel helper for SotaOCR + OpenAI API routing on Windows."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPLIT_CONFIG = PROJECT_ROOT / "config" / "wireguard" / "vpn188958_split_sotaocr.conf"
SPLIT_SERVICE = "WireGuardTunnel$vpn188958_split_sotaocr"
ENSURE_SCRIPT = PROJECT_ROOT / "scripts" / "ensure_sotaocr_vpn.ps1"


def split_config_path() -> Path:
    raw = (os.environ.get("SOTAOCR_WG_CONFIG") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path
    return DEFAULT_SPLIT_CONFIG


def is_split_tunnel_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Service -Name '{SPLIT_SERVICE}' -ErrorAction SilentlyContinue).Status",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "Running" in (completed.stdout or "")


def ensure_api_vpn(*, raise_on_failure: bool = False) -> bool:
    """Start split-tunnel WireGuard for SotaOCR and OpenAI API if installed."""
    if sys.platform != "win32":
        return True
    if is_split_tunnel_running():
        return True
    if not ENSURE_SCRIPT.is_file():
        msg = f"API VPN script missing: {ENSURE_SCRIPT}"
        if raise_on_failure:
            raise RuntimeError(msg)
        logger.warning(msg)
        return False
    env = os.environ.copy()
    env["SOTAOCR_WG_CONFIG"] = str(split_config_path())
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ENSURE_SCRIPT),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if raise_on_failure:
            raise RuntimeError(f"Failed to start API VPN: {exc}") from exc
        logger.warning("Failed to start API VPN: %s", exc)
        return False
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if raise_on_failure:
            raise RuntimeError(f"API VPN script failed: {detail}")
        logger.warning("API VPN script failed: %s", detail)
        return False
    if not is_split_tunnel_running():
        msg = f"API VPN split tunnel is not running ({SPLIT_SERVICE})"
        if raise_on_failure:
            raise RuntimeError(msg)
        logger.warning(msg)
        return False
    return True


def ensure_recognition_vpn_ok() -> None:
    """Hot-path guard for recognition APIs (SotaOCR + OpenAI) on Windows dev.

    On non-Windows (production / VPS) the tunnel is a deployment concern, so
    this is a no-op. On Windows it performs only a **fast** state check and
    raises :class:`UserFacingError` (code ``vpn_unavailable``) if the tunnel
    is down — it never tries to (re)start the tunnel from the request path,
    avoiding the previous ~120 s blocking behaviour. Worker startup is
    responsible for bringing the tunnel up once; the Windows service keeps it
    alive (auto-restart).
    """
    from app.errors import UserFacingError

    if sys.platform != "win32":
        return
    if not is_split_tunnel_running():
        logger.warning("Recognition VPN tunnel is down; rejecting request fast")
        raise UserFacingError(
            "Сервис распознавания временно недоступен. Попробуйте через минуту.",
            hint="Если ошибка повторяется, проверьте VPN-туннель.",
            code="vpn_unavailable",
        )


ensure_sotaocr_vpn = ensure_api_vpn
