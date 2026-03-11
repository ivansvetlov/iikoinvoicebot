"""Единый реестр пользовательских кодов событий Telegram-бота."""

from __future__ import annotations

from dataclasses import dataclass

BOT_BACKEND_UNAVAILABLE = "BOT_BACKEND_UNAVAILABLE"
BOT_RATE_LIMIT = "BOT_RATE_LIMIT"
BOT_NO_PENDING = "BOT_NO_PENDING"
# Исторический код: использовался при старом UX с автотаймером pending.
BOT_PENDING_TIMEOUT = "BOT_PENDING_TIMEOUT"


@dataclass(frozen=True)
class BotEventCodeMeta:
    """Метаданные кода события для документации и отладки."""

    code: str
    status: str
    emitted_from: str
    meaning: str
    user_action: str


BOT_EVENT_CODE_REGISTRY: dict[str, BotEventCodeMeta] = {
    BOT_BACKEND_UNAVAILABLE: BotEventCodeMeta(
        code=BOT_BACKEND_UNAVAILABLE,
        status="active",
        emitted_from=(
            "app/bot/manager.py: _process_pending_as_batch_chat, "
            "_finalize_media_group, _finalize_split"
        ),
        meaning="Бот не смог отправить файл(ы) в backend после ретраев.",
        user_action="Проверить доступность backend/сети и повторить отправку позже.",
    ),
    BOT_RATE_LIMIT: BotEventCodeMeta(
        code=BOT_RATE_LIMIT,
        status="active",
        emitted_from="app/bot/manager.py: _handle_document, _handle_photo",
        meaning="Сработал лимит частоты файлов на пользователя.",
        user_action="Подождать около минуты и отправить файл(ы) снова.",
    ),
    BOT_NO_PENDING: BotEventCodeMeta(
        code=BOT_NO_PENDING,
        status="active",
        emitted_from="app/bot/manager.py: on_mode_choice",
        meaning="Пользователь нажал action-кнопку без ожидающих файлов.",
        user_action="Отправить файл(ы) заново и выбрать действие на актуальной кнопке.",
    ),
    BOT_PENDING_TIMEOUT: BotEventCodeMeta(
        code=BOT_PENDING_TIMEOUT,
        status="archive",
        emitted_from="Не эмитится с 2026-03-10 (убран скрытый pending-таймер).",
        meaning="Таймер pending истекал до явного выбора пользователя.",
        user_action="Н/Д (архивное поведение).",
    ),
}


def event_line(code: str) -> str:
    """Строка с кодом события в едином формате."""

    return f"Код события: {code}"


def append_event_code(message: str, code: str) -> str:
    """Добавляет код события к пользовательскому сообщению."""

    return f"{message.rstrip()}\n{event_line(code)}"
