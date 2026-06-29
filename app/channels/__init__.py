"""Адаптеры каналов (Telegram, MAX) для invoice-бота."""

from app.channels.protocol import (
    ChannelKind,
    ChannelPort,
    IncomingEvent,
    IncomingFile,
    IncomingKind,
    OutgoingAction,
    OutgoingEdit,
    OutgoingMessage,
)

__all__ = [
    "ChannelKind",
    "ChannelPort",
    "IncomingEvent",
    "IncomingFile",
    "IncomingKind",
    "OutgoingAction",
    "OutgoingEdit",
    "OutgoingMessage",
]
