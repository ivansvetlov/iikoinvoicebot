"""Идентификация канала пользователя по store-id.

Store-id Telegram — это число (chat_id), MAX — строка с префиксом ``max:``.
Префикс определён один раз здесь, чтобы не размножать магические строки.
"""
from __future__ import annotations

from typing import Literal

from app.channels.protocol import ChannelKind

#: Префикс store-id для пользователей канала MAX.
MAX_PREFIX = "max:"

ChannelName = Literal["telegram", "max"]


def is_max_channel_user(user_id: str | None) -> bool:
    """Вернуть True, если ``user_id`` относится к каналу MAX."""
    return bool(user_id and str(user_id).startswith(MAX_PREFIX))


def channel_of(user_id: str | None) -> ChannelKind:
    """Определить ``ChannelKind`` по store-id пользователя."""
    return ChannelKind.MAX if is_max_channel_user(user_id) else ChannelKind.TELEGRAM


def should_use_max_hybrid_only(
    user_id: str | None,
    *,
    source_type: str,
    use_fast_parser: bool,
) -> bool:
    """MAX images: SotaOCR hybrid path only (no vision/race) when enabled in settings."""
    from app.config import settings

    return (
        not use_fast_parser
        and source_type == "image"
        and is_max_channel_user(user_id)
        and bool(getattr(settings, "max_recognition_hybrid_only", True))
    )
