"""Probe MAX API: /me, send test DM, compare same token from two logical bots."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values
from maxapi import Bot
from maxapi.enums.parse_mode import ParseMode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_USER_ID = 183900520  # from grok_max_bridge sessions.json
API_BASES = ("https://platform-api2.max.ru", "https://platform-api.max.ru")


def _token() -> str:
    env = dotenv_values(PROJECT_ROOT / ".env")
    return (
        (env.get("MAX_INVOICE_BOT_TOKEN") or "").strip()
        or (env.get("GROK_MAX_BRIDGE_TOKEN") or "").strip()
    )


async def _close(bot: Bot) -> None:
    session = getattr(bot, "session", None)
    if session and not session.closed:
        await session.close()


async def probe_me(token: str, label: str) -> dict:
    bot = Bot(token, parse_mode=ParseMode.HTML)
    try:
        me = await bot.get_me()
        data = {
            "label": label,
            "user_id": getattr(me, "user_id", None),
            "username": getattr(me, "username", None),
            "first_name": getattr(me, "first_name", None) or getattr(me, "name", None),
            "is_bot": getattr(me, "is_bot", None),
        }
        return data
    finally:
        await _close(bot)


async def send_test(token: str, label: str, user_id: int) -> dict:
    bot = Bot(token, parse_mode=ParseMode.HTML)
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    text = f"<b>probe {label}</b>\nТест {stamp}\nОдин токен, разные процессы."
    try:
        result = await bot.send_message(user_id=user_id, text=text)
        mid = getattr(result, "message_id", None) or getattr(result, "id", None)
        return {"label": label, "ok": True, "message_id": mid}
    except Exception as exc:  # noqa: BLE001
        return {"label": label, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await _close(bot)


def raw_get(path: str, token: str) -> dict:
    headers = {"Authorization": token}
    last_err = ""
    for base in API_BASES:
        try:
            r = httpx.get(f"{base}{path}", headers=headers, timeout=20)
            return {"base": base, "status": r.status_code, "body": r.json() if r.content else {}}
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
    return {"error": last_err}


async def main() -> int:
    token = _token()
    if not token:
        print("No MAX token in .env (MAX_INVOICE_BOT_TOKEN / GROK_MAX_BRIDGE_TOKEN)")
        return 1

    print("=== /me (invoice label) ===")
    me1 = await probe_me(token, "invoice")
    print(json.dumps(me1, ensure_ascii=False, indent=2))

    print("\n=== /me (bridge label, same token) ===")
    me2 = await probe_me(token, "bridge")
    print(json.dumps(me2, ensure_ascii=False, indent=2))
    print("same_identity:", me1 == me2)

    print("\n=== raw GET /subscriptions ===")
    print(json.dumps(raw_get("/subscriptions", token), ensure_ascii=False, indent=2))

    print(f"\n=== send DM to user {TEST_USER_ID} ===")
    s1 = await send_test(token, "invoice-process", TEST_USER_ID)
    await asyncio.sleep(1)
    s2 = await send_test(token, "bridge-process", TEST_USER_ID)
    print(json.dumps({"invoice": s1, "bridge": s2}, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
