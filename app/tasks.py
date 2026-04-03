"""Задачи воркера (RQ).

Этот модуль запускается воркером и делает две вещи:
1) обрабатывает файл через пайплайн
2) редактирует (или отправляет) сообщение в Telegram с результатом

Важно: пользователю не показываем технические детали ошибок.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from app.config import settings
from app.observability import append_metric
from app.services.pipeline import InvoicePipelineService
from app.task_store import mark_done, mark_error, mark_processing
from app.utils.user_messages import format_user_response, format_invoice_markdown

logger = logging.getLogger(__name__)


def _send_telegram_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        httpx.post(url, json=payload, timeout=20)
    except Exception:
        # deliberately ignore to not crash the worker
        return


def _edit_telegram_message(
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: dict | None = None,
) -> bool:
    if not settings.telegram_bot_token:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        httpx.post(url, json=payload, timeout=20)
        return True
    except Exception:
        return False


def _to_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    return {"status": "error", "message": "Неизвестный формат результата."}


def process_invoice_task(payload_path: str) -> dict[str, Any]:
    """Worker entrypoint: обрабатывает одну задачу и уведомляет пользователя."""
    started = perf_counter()
    payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
    filename = payload.get("filename")
    file_path = payload.get("file_path")
    files = payload.get("files")
    user_id = payload.get("user_id")
    chat_id = payload.get("chat_id")
    status_message_id = payload.get("status_message_id")
    push_to_iiko = payload.get("push_to_iiko", True)
    pdf_mode = payload.get("pdf_mode")
    request_id = payload.get("request_id")
    logger.info("Worker task started", extra={"request_id": request_id})
    if request_id:
        mark_processing(request_id)

    is_batch = bool(files)
    if is_batch and (not isinstance(files, list) or not files):
        is_batch = False
    if not is_batch and (not filename or not file_path):
        result = {
            "status": "error",
            "message": "Пустой payload: нет файла для обработки.",
            "request_id": request_id,
        }
        if request_id:
            mark_error(request_id, result["message"], "missing filename/file_path")
        if chat_id:
            text = _format_response(result)
            if status_message_id:
                if not _edit_telegram_message(chat_id, status_message_id, text):
                    _send_telegram_message(chat_id, text)
            else:
                _send_telegram_message(chat_id, text)
        append_metric(
            "worker.task.finished",
            request_id=request_id,
            status=result.get("status"),
            error_code="missing_payload",
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return result

    pipeline = InvoicePipelineService()

    async def _run() -> dict[str, Any]:
        if is_batch:
            file_payload: list[tuple[str, bytes]] = []
            for file_name, path in files:
                file_payload.append((file_name, Path(path).read_bytes()))
            return await pipeline.process_batch(
                file_payload,
                push_to_iiko=push_to_iiko,
                user_id=user_id,
                pdf_mode=pdf_mode,
                request_id=request_id,
            )
        content = Path(file_path).read_bytes()
        return await pipeline.process(
            filename,
            content,
            push_to_iiko=push_to_iiko,
            user_id=user_id,
            pdf_mode=pdf_mode,
            request_id=request_id,
        )

    try:
        result = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Worker task crashed",
            extra={"request_id": request_id, "event_code": "WORKER_TASK_EXCEPTION"},
        )
        # Не отправляем пользователю технические детали; они остаются в task_store/backend.log.
        result = {
            "status": "error",
            "message": "Не удалось обработать файл на сервере. Попробуйте ещё раз или отправьте файл в другом формате.",
            "iiko_error": str(exc),
            "request_id": request_id,
        }

    result_payload = _to_payload(result)

    if request_id:
        if result_payload.get("status") == "error":
            mark_error(
                request_id,
                result_payload.get("message", ""),
                result_payload.get("iiko_error"),
            )
        else:
            mark_done(request_id, result_payload)

    if chat_id:
        text = _format_response(result_payload)
        reply_markup = None
        if result_payload.get("status") == "ok":
            text = format_invoice_markdown(result_payload)
            reply_markup = _build_invoice_actions(result_payload.get("request_id"))
        if status_message_id:
            if not _edit_telegram_message(chat_id, status_message_id, text, reply_markup):
                _send_telegram_message(chat_id, text, reply_markup)
        else:
            _send_telegram_message(chat_id, text, reply_markup)
    status = result_payload.get("status")
    error_code = result_payload.get("error_code")
    duration_ms = round((perf_counter() - started) * 1000, 2)
    logger.info(
        "Worker task finished",
        extra={"request_id": request_id, "status": status, "duration_ms": duration_ms},
    )
    append_metric(
        "worker.task.finished",
        request_id=request_id,
        status=status,
        error_code=error_code,
        duration_ms=duration_ms,
        has_chat=bool(chat_id),
    )
    return result_payload


def _format_response(payload: dict[str, Any]) -> str:
    # Используем единый формат для бота и воркера.
    return format_user_response(payload)


def _build_invoice_actions(request_id: str | None) -> dict | None:
    if not request_id:
        return None
    return {
        "inline_keyboard": [
            [
                {"text": "✏ Редактировать", "callback_data": f"inv:edit:{request_id}"},
                {"text": "✅ Отправить в iiko", "callback_data": f"inv:send:{request_id}"},
            ],
            [
                {"text": "✖ Отмена", "callback_data": f"inv:cancel:{request_id}"},
            ],
        ]
    }
