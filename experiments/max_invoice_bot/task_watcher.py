"""Poll task_store and deliver worker results to MAX (no TG push)."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from maxapi import Bot

from app.bot.invoice_keyboards import build_invoice_actions, build_retry_actions
from app.task_store import get_task
from app.utils.user_messages import format_invoice_markdown, format_user_response
from experiments.max_invoice_bot.messaging import reply_or_edit, send_to_user, split_text

logger = logging.getLogger(__name__)

TERMINAL = frozenset({"done", "error", "completed", "failed"})


def _normalize_status(raw: str | None) -> str:
    s = str(raw or "").strip().lower()
    if s in ("done", "completed"):
        return "done"
    if s in ("error", "failed"):
        return "error"
    return s


def _result_from_task(task: dict[str, Any]) -> dict[str, Any]:
    rid = task.get("request_id")
    if not rid:
        return {"status": "error", "message": "Нет request_id."}
    path = Path(__file__).resolve().parents[2] / "logs" / "requests" / f"{rid}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    status = _normalize_status(task.get("status"))
    if status == "done":
        return {"status": "ok", "request_id": rid, "message": task.get("message") or "Готово."}
    return {
        "status": "error",
        "request_id": rid,
        "message": task.get("message") or "Ошибка обработки.",
        "error_code": task.get("error") or "task_error",
    }


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
    max_wait_sec: float = 600.0,
) -> None:
    """Poll until task completes, then send/edit result in MAX."""
    elapsed = 0.0
    last_ping = 0.0
    while elapsed < max_wait_sec:
        task = get_task(request_id)
        if task:
            status = _normalize_status(task.get("status"))
            if status in TERMINAL or status in ("done", "error"):
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
        if elapsed - last_ping >= 8.0 and status_message_id:
            try:
                msg = await bot.get_message(message_id=status_message_id)
                if msg:
                    await msg.edit(text="⏳ Обрабатываю накладную…", format=None)
            except Exception:
                pass
            last_ping = elapsed
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    await send_to_user(
        bot,
        chat_id=chat_id,
        user_id=user_id,
        text="⏱ Превышено время ожидания. Проверьте /status или отправьте файл снова.",
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
