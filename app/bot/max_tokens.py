"""MAX messenger bot token helpers — keep invoice and grok bridge tokens separate."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from maxapi import Bot

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MaxBotIdentity:
    label: str
    username: str | None
    user_id: int | None


def assert_distinct_max_tokens(
    invoice_token: str,
    bridge_token: str,
    *,
    invoice_var: str = "MAX_INVOICE_BOT_TOKEN",
    bridge_var: str = "GROK_MAX_BRIDGE_TOKEN",
) -> None:
    inv = (invoice_token or "").strip()
    br = (bridge_token or "").strip()
    if inv and br and inv == br:
        raise RuntimeError(
            f"{invoice_var} and {bridge_var} must be different bot tokens. "
            "Pusher (invoice) uses MAX_INVOICE_BOT_TOKEN; grok bridge needs its own bot on business.max.ru."
        )


async def _probe(token: str, label: str) -> MaxBotIdentity:
    bot = Bot(token)
    try:
        me = await bot.get_me()
        return MaxBotIdentity(
            label=label,
            username=getattr(me, "username", None),
            user_id=getattr(me, "user_id", None),
        )
    finally:
        session = getattr(bot, "session", None)
        if session and not session.closed:
            await session.close()


def probe_max_bot(token: str, label: str) -> MaxBotIdentity:
    return asyncio.run(_probe(token, label))


def _read_env_tokens() -> tuple[str, str]:
    invoice = os.environ.get("MAX_INVOICE_BOT_TOKEN", "").strip()
    bridge = os.environ.get("GROK_MAX_BRIDGE_TOKEN", "").strip()
    if invoice or bridge:
        return invoice, bridge
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return "", ""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return invoice, bridge
    values = dotenv_values(env_path)
    return (
        (values.get("MAX_INVOICE_BOT_TOKEN") or "").strip(),
        (values.get("GROK_MAX_BRIDGE_TOKEN") or "").strip(),
    )


def validate_max_bot_tokens_from_env() -> None:
    assert_distinct_max_tokens(*_read_env_tokens())
