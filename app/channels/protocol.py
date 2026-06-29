"""Контракт канала доставки (Telegram, MAX, …) для invoice-бота.

Бизнес-логика живёт в InvoiceBotController (Phase 2); адаптеры каналов
реализуют ChannelPort и не содержат сценариев auth/split/posting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class ChannelKind(str, Enum):
    TELEGRAM = "telegram"
    MAX = "max"


class IncomingKind(str, Enum):
    COMMAND = "command"
    TEXT = "text"
    FILE = "file"
    CALLBACK = "callback"
    BOT_STARTED = "bot_started"


@dataclass(slots=True)
class IncomingFile:
    filename: str
    mime_type: str | None
    size: int | None
    # Адаптер заполняет один из вариантов для download()
    native_attachment: Any = None


@dataclass(slots=True)
class IncomingEvent:
    kind: IncomingKind
    user_id: str
    channel: ChannelKind
    text: str | None = None
    command: str | None = None
    callback_data: str | None = None
    files: list[IncomingFile] = field(default_factory=list)
    reply_to_message_id: str | None = None
    native_event: Any = None


@dataclass(slots=True)
class OutgoingMessage:
    text: str
    keyboard: dict[str, Any] | None = None
    parse_mode: str = "html"


@dataclass(slots=True)
class OutgoingEdit:
    message_id: str
    text: str
    keyboard: dict[str, Any] | None = None
    parse_mode: str = "html"


@dataclass(slots=True)
class OutgoingPin:
    message_id: str


@dataclass(slots=True)
class OutgoingDelete:
    message_id: str


@dataclass(slots=True)
class OutgoingAction:
    """Единый ответ controller → adapter."""

    send: OutgoingMessage | None = None
    edit: OutgoingEdit | None = None
    pin: OutgoingPin | None = None
    delete: OutgoingDelete | None = None


@runtime_checkable
class ChannelPort(Protocol):
    """Минимальный интерфейс, который InvoiceBotController использует для UI."""

    kind: ChannelKind

    async def apply(self, user_id: str, action: OutgoingAction) -> str | None:
        """Выполнить исходящее действие. Возвращает message_id при send."""

    async def download(self, file: IncomingFile, dest_dir: str) -> str:
        """Скачать вложение во временный путь; вернуть local path."""

    def map_incoming(self, native_event: Any) -> IncomingEvent | None:
        """Преобразовать событие SDK в нейтральное."""
