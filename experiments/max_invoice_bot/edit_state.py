"""Edit flow state (ported from app.bot.manager)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EditState:
    request_id: str
    payload: dict[str, Any]
    overrides: dict[str, str] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    mode: str | None = None
    awaiting: str | None = None
    item_index: int | None = None

    def __post_init__(self) -> None:
        parsed = self.payload.get("parsed") or {}
        if not self.items:
            self.items = list(parsed.get("items") or self.payload.get("items") or [])
