"""Convert neutral invoice keyboard dicts to maxapi inline_keyboard."""
from __future__ import annotations

from typing import Any

from maxapi.types.attachments.buttons import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def dict_to_markup(markup: dict[str, Any] | None):
    if not markup:
        return None
    rows = markup.get("inline_keyboard") or []
    if not rows:
        return None
    kb = InlineKeyboardBuilder()
    for row in rows:
        buttons = []
        for btn in row:
            text = str(btn.get("text") or "")
            payload = str(btn.get("callback_data") or "")
            if not text or not payload:
                continue
            buttons.append(CallbackButton(text=text, payload=payload))
        if buttons:
            kb.row(*buttons)
    built = kb.as_markup()
    return built if built else None
