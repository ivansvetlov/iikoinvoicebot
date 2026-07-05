"""Poll task_store and deliver worker results to MAX (no TG push)."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from maxapi import Bot

from app.bot.invoice_keyboards import build_invoice_actions, build_retry_actions
from app.bot.messages import Msg
from app.config import settings
from app.task_store import get_task
from app.utils.user_messages import format_invoice_markdown, format_user_response
from experiments.max_invoice_bot.messaging import reply_or_edit, send_to_user
from experiments.max_invoice_bot.processing_status import processing_stage_message

logger = logging.getLogger(__name__)

TERMINAL = frozenset({"done", "error", "completed", "failed"})


def _normalize_status(raw: str | None) -> str:
    s = str(raw or "").strip().lower()
    if s in ("done", "completed", "ok"):
        return "done"
    if s in ("error", "failed"):
        return "error"
    return s


def _result_from_task(task: dict[str, Any]) -> dict[str, Any]:
    rid = task.get("request_id")
    if not rid:
        return {"status": "error", "message": "Нет request_id."}
    payload: dict[str, Any] = {}
    path = Path(__file__).resolve().parents[2] / "logs" / "requests" / f"{rid}.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    status = _normalize_status(task.get("status"))
    if status == "done":
        payload["status"] = "ok"
        payload.setdefault("request_id", rid)
        payload.setdefault("message", task.get("message") or "Готово.")
        if task.get("iiko_uploaded") is not None:
            payload["iiko_uploaded"] = bool(task.get("iiko_uploaded"))
        return payload
    payload["status"] = "error"
    payload.setdefault("request_id", rid)
    payload.setdefault("message", task.get("message") or "Ошибка обработки.")
    payload.setdefault("error_code", task.get("error") or "task_error")
    return payload


def _keyboard_for_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("status") == "ok":
        allow_send = not bool(payload.get("iiko_uploaded"))
        allow_sync = not bool(payload.get("nomenclature_synced"))
        return build_invoice_actions(
            payload.get("request_id"),
            allow_send=allow_send,
            allow_sync=allow_sync,
        )
    if payload.get("status") == "error":
        return build_retry_actions(payload.get("request_id"), payload.get("error_code"))
    return None


async def watch_and_deliver(
    bot: Bot,
    *,
    chat_id: int | None,
    user_id: int,
    request_id: str,
    status_message_id: str | None = None,
    poll_interval: float = 2.0,
    max_wait_sec: float | None = None,
) -> None:
    """Poll until task completes, then send/edit result in MAX."""
    if max_wait_sec is None:
        race_limit = int(getattr(settings, "recognition_race_budget_sec", 90) or 90)
        watch_limit = int(getattr(settings, "max_watch_timeout_sec", 0) or 0)
        default_watch = race_limit + 60
        max_wait_sec = float(max(60, watch_limit or default_watch))
    elapsed = 0.0
    last_ping = -8.0
    stage_interval = 8.0
    while elapsed < max_wait_sec:
        task = get_task(request_id)
        if task:
            status = _normalize_status(task.get("status"))
            if status in TERMINAL:
                payload = _result_from_task(task)
                text = (
                    format_invoice_markdown(payload)
                    if payload.get("status") == "ok"
                    else format_user_response(payload)
                )
                keyboard = _keyboard_for_result(payload)
                if status_message_id:
                    try:
                        msg = await bot.get_message(message_id=status_message_id)
                        if msg:
                            await reply_or_edit(msg, text, keyboard)
                            return
                    except Exception:
                        logger.debug("Could not edit status message %s", status_message_id)
                await send_to_user(
                    bot,
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    keyboard=keyboard,
                )
                return
        if elapsed - last_ping >= stage_interval and status_message_id:
            try:
                msg = await bot.get_message(message_id=status_message_id)
                if msg:
                    await msg.edit(
                        text=processing_stage_message(elapsed, interval_sec=stage_interval),
                        attachments=[],
                        format=None,
                    )
            except Exception:
                pass
            last_ping = elapsed
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    await send_to_user(
        bot,
        chat_id=chat_id,
        user_id=user_id,
        text=Msg.STATUS_TIMEOUT,
    )


def schedule_watch(
    bot: Bot,
    *,
    chat_id: int | None,
    max_user_id: int,
    request_id: str,
    status_message_id: str | None = None,
) -> asyncio.Task[None]:
    return asyncio.create_task(
        watch_and_deliver(
            bot,
            chat_id=chat_id,
            user_id=max_user_id,
            request_id=request_id,
            status_message_id=status_message_id,
        ),
        name=f"max-watch-{request_id[:12]}",
    )
