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
from app.channels.users import (
    MAX_PREFIX,
    channel_of,
    is_max_channel_user,
)

__all__ = [
    "ChannelKind",
    "ChannelPort",
    "IncomingEvent",
    "IncomingFile",
    "IncomingKind",
    "MAX_PREFIX",
    "OutgoingAction",
    "OutgoingEdit",
    "OutgoingMessage",
    "channel_of",
    "is_max_channel_user",
]
