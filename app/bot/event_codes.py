"""Единые коды событий Telegram-бота и helper для user-facing сообщений."""

from __future__ import annotations

BOT_RATE_LIMIT = "BOT_RATE_LIMIT"
BOT_BACKEND_UNAVAILABLE = "BOT_BACKEND_UNAVAILABLE"
BOT_NO_PENDING = "BOT_NO_PENDING"
BOT_PENDING_TIMEOUT = "BOT_PENDING_TIMEOUT"

SHORT_EVENT_CODES = {
    BOT_RATE_LIMIT: "4101",
    BOT_BACKEND_UNAVAILABLE: "4501",
    BOT_NO_PENDING: "4201",
    BOT_PENDING_TIMEOUT: "4202",
}

ALL_BOT_EVENT_CODES = {
    BOT_RATE_LIMIT,
    BOT_BACKEND_UNAVAILABLE,
    BOT_NO_PENDING,
    BOT_PENDING_TIMEOUT,
}


def event_short_code(code: str) -> str:
    """Короткий пользовательский код (4 цифры) для отображения в чате."""
    return SHORT_EVENT_CODES.get(code, "4999")


def event_meta(code: str) -> dict[str, str]:
    """Данные для логов: внутренний + короткий код."""
    return {
        "event_code": code,
        "event_short": event_short_code(code),
    }


def with_event_code(message: str, code: str) -> str:
    """Добавляет строку с коротким кодом события в ответ пользователю."""
    return f"{message}\nКод: {event_short_code(code)}"
