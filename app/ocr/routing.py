"""Recognition API routing: WireGuard split-tunnel vs GeoHide DNS+proxy."""
from __future__ import annotations

import logging
import socket
import sys
from typing import Iterable

from app.config import settings

logger = logging.getLogger(__name__)

GEOHIDE_PROXY_IPS = frozenset({"45.155.204.190", "37.230.192.51", "31.25.239.132"})
GEOHIDE_OPENAI_HOST = "api.openai.com"


def recognition_route() -> str:
    raw = (settings.recognition_route or "wireguard").strip().lower()
    if raw in {"geohide", "geo-hide", "geo_hide", "dns"}:
        return "geohide"
    if raw in {"none", "off", "direct"}:
        return "none"
    return "wireguard"


def _resolve_ipv4(host: str) -> set[str]:
    try:
        infos = socket.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except OSError:
        return set()
    return {str(item[4][0]) for item in infos}


def geohide_openai_ips() -> set[str]:
    return _resolve_ipv4(GEOHIDE_OPENAI_HOST)


def is_geohide_route_ok(*, proxy_ips: Iterable[str] | None = None) -> bool:
    """True when api.openai.com resolves to GeoHide proxy IPs (hosts or AdGuard rewrite)."""
    expected = set(proxy_ips or GEOHIDE_PROXY_IPS)
    resolved = geohide_openai_ips()
    if resolved & expected:
        return True
    logger.debug(
        "GeoHide DNS check failed for %s: resolved=%s expected=%s",
        GEOHIDE_OPENAI_HOST,
        sorted(resolved),
        sorted(expected),
    )
    return False


def is_local_geohide_stack_listening() -> bool:
    """Best-effort: AdGuard (53/853/444) and Sing-box (80/443) on localhost."""
    if sys.platform != "win32":
        return False
    ports = (53, 80, 443, 444, 853)
    for port in ports:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            continue
    return False