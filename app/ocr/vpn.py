"""WireGuard split-tunnel helper for SotaOCR + OpenAI API routing on Windows."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from app.utils.subprocess_hidden import hidden_subprocess_kwargs, run_hidden

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
        completed = run_hidden(["sc", "query", SPLIT_SERVICE], timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    raw = (completed.stdout or b"") + (completed.stderr or b"")
    text = raw.decode("cp866", errors="replace")
    return "RUNNING" in text.upper()


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
                "-WindowStyle",
                "Hidden",
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
            **hidden_subprocess_kwargs(),
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
    avoiding the previous ~120 s blocking behaviour.

    Lifecycle model: the tunnel is an explicit dev component ("8. vpn" /
    ``scripts/vpn_ctl.py``). Worker startup brings it up via
    ``ensure_api_vpn`` (which self-elevates through the PowerShell helper).
    Stopping it requires administrator rights and is done explicitly via
    ``scripts/vpn_ctl.py down`` — it is NOT tied to worker shutdown, because
    the worker normally runs without elevation and cannot stop the service.
    """
    from app.errors import UserFacingError

    if sys.platform != "win32":
        return
    if not is_split_tunnel_running():
        logger.warning("Recognition VPN tunnel is down; rejecting request fast")
        raise UserFacingError(
            "Сервис распознавания временно недоступен. Попробуйте через минуту.",
            hint="Если ошибка повторяется, проверьте VPN-туннель (`scripts/vpn_ctl.py status`).",
            code="vpn_unavailable",
        )


def stop_tunnel(*, timeout: int = 30) -> bool:
    """Stop the split-tunnel service (Windows only).

    Used by ``scripts/vpn_ctl.py down``. Requires administrator rights (the
    Windows service cannot be stopped from a non-elevated process); callers
    that may be non-elevated should self-elevate (see ``_elevated`` in
    vpn_ctl). Returns True if the service is stopped (or was not running).
    No-op on non-Windows.
    """
    if sys.platform != "win32":
        return True
    if not is_split_tunnel_running():
        return True
    try:
        run_hidden(
            ["sc", "stop", SPLIT_SERVICE],
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Failed to stop VPN tunnel: %s", exc)
        return False
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_split_tunnel_running():
            logger.info("VPN tunnel stopped")
            return True
        time.sleep(0.5)
    logger.warning("VPN tunnel did not stop within %ss", timeout)
    return False


ensure_sotaocr_vpn = ensure_api_vpn
