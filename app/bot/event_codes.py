"""Единые коды событий Telegram-бота и helper для user-facing сообщений."""

from __future__ import annotations

BOT_RATE_LIMIT = "BOT_RATE_LIMIT"
BOT_BACKEND_UNAVAILABLE = "BOT_BACKEND_UNAVAILABLE"
BOT_NO_PENDING = "BOT_NO_PENDING"
BOT_PENDING_TIMEOUT = "BOT_PENDING_TIMEOUT"

ALL_BOT_EVENT_CODES = {
    BOT_RATE_LIMIT,
    BOT_BACKEND_UNAVAILABLE,
    BOT_NO_PENDING,
    BOT_PENDING_TIMEOUT,
}


def with_event_code(message: str, code: str) -> str:
    """Добавляет строку с кодом события в ответ пользователю."""
    return f"{message}\nКод события: {code}"
