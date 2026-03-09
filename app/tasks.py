"""Задачи воркера (RQ).

Этот модуль запускается воркером и делает две вещи:
1) обрабатывает файл через пайплайн
2) редактирует (или отправляет) сообщение в Telegram с результатом

Важно: пользователю не показываем технические детали ошибок.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.services.pipeline import InvoicePipelineService
from app.task_store import mark_done, mark_error, mark_processing
from app.utils.user_messages import format_user_response


def _send_telegram_message(chat_id: int, text: str) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        httpx.post(url, json=payload, timeout=20)
    except Exception:
        # deliberately ignore to not crash the worker
        return


def _edit_telegram_message(chat_id: int, message_id: int, text: str) -> bool:
    if not settings.telegram_bot_token:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
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
    if request_id:
        mark_processing(request_id)

    if files:
        filename, file_path = files[0]
        payload["filename"] = filename
        payload["file_path"] = file_path
    if not filename or not file_path:
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
        return result

    content = Path(file_path).read_bytes()
    pipeline = InvoicePipelineService()

    async def _run() -> dict[str, Any]:
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
        if status_message_id:
            if not _edit_telegram_message(chat_id, status_message_id, text):
                _send_telegram_message(chat_id, text)
        else:
            _send_telegram_message(chat_id, text)
    return result_payload


def _format_response(payload: dict[str, Any]) -> str:
    # Используем единый формат для бота и воркера.
    return format_user_response(payload)

