"""Rotating processing status lines for MAX task watcher."""
from __future__ import annotations

from app.bot.messages import Msg


def processing_stage_message(elapsed_sec: float, *, interval_sec: float = 8.0) -> str:
    stages = Msg.PROCESSING_STAGES or (Msg.STATUS_PROCESSING_PING,)
    if not stages:
        return Msg.STATUS_PROCESSING_PING
    index = int(max(0.0, elapsed_sec) // max(1.0, interval_sec)) % len(stages)
    return stages[index]
