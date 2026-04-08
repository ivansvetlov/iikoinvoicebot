"""Клиент для отправки файлов в backend из Telegram-бота."""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import httpx

from app.config import settings
from app.services.user_store import get_pdf_mode

logger = logging.getLogger(__name__)


async def send_file_to_backend(
    backend_url: str,
    filename: str,
    content: bytes,
    user_id: str | None,
    chat_id: int | None,
    status_message_id: int | None = None,
    push_to_iiko_override: bool | None = None,
) -> dict:
    """Отправляет один файл в backend и возвращает JSON-ответ."""
    logger.info("Sending file to backend: %s", filename)

    async with httpx.AsyncClient(timeout=300) as client:
        for attempt in range(3):
            try:
                push_to_iiko = settings.push_to_iiko if push_to_iiko_override is None else push_to_iiko_override
                data: dict[str, str] = {
                    "push_to_iiko": "true" if push_to_iiko else "false",
                }
                if user_id:
                    data["user_id"] = user_id
                    data["pdf_mode"] = get_pdf_mode(user_id)
                if chat_id:
                    data["chat_id"] = str(chat_id)
                if status_message_id:
                    data["status_message_id"] = str(status_message_id)

                response = await client.post(
                    f"{backend_url.rstrip('/')}/process",
                    files={"file": (filename, content)},
                    data=data,
                )
                try:
                    return response.json()
                except ValueError:
                    response.raise_for_status()
                    raise
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                logger.warning("Backend unavailable, attempt %s", attempt + 1)
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
                    continue
                raise exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning("Backend status error: %s", status_code)

                if status_code == 413:
                    return {
                        "status": "error",
                        "message": f"Файл слишком большой. Максимум {settings.max_upload_mb} MB.",
                    }
                if status_code == 422:
                    return {
                        "status": "error",
                        "message": "Не удалось обработать запрос. Проверьте файл и попробуйте снова.",
                    }
                if status_code == 429:
                    return {
                        "status": "error",
                        "message": "Сервис перегружен. Попробуйте отправить файл чуть позже.",
                    }
                return {
                    "status": "error",
                    "message": "Сервер временно недоступен. Попробуйте позже.",
                }


async def send_batch_to_backend(
    backend_url: str,
    files: Iterable[tuple[str, bytes]],
    user_id: str | None,
    chat_id: int | None,
    status_message_id: int | None = None,
    push_to_iiko_override: bool | None = None,
) -> dict:
    """Отправляет несколько файлов одной накладной в backend."""
    files = list(files)
    logger.info("Sending batch to backend: %s files", len(files))

    async with httpx.AsyncClient(timeout=300) as client:
        for attempt in range(3):
            try:
                push_to_iiko = settings.push_to_iiko if push_to_iiko_override is None else push_to_iiko_override
                data: dict[str, str] = {
                    "push_to_iiko": "true" if push_to_iiko else "false",
                }
                if user_id:
                    data["user_id"] = user_id
                    data["pdf_mode"] = get_pdf_mode(user_id)
                if chat_id:
                    data["chat_id"] = str(chat_id)
                if status_message_id:
                    data["status_message_id"] = str(status_message_id)

                payload = [("files", (name, content)) for name, content in files]
                response = await client.post(
                    f"{backend_url.rstrip('/')}/process-batch",
                    files=payload,
                    data=data,
                )
                try:
                    return response.json()
                except ValueError:
                    response.raise_for_status()
                    raise
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                logger.warning("Backend unavailable, attempt %s", attempt + 1)
                if attempt < 2:
                    await asyncio.sleep(1 + attempt)
                    continue
                raise exc
