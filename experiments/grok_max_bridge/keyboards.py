"""MAX inline keyboards for bridge bot."""
from __future__ import annotations

from maxapi.types.attachments.buttons import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder


def main_menu():
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="🆕 Новая сессия", payload="act:new"),
        CallbackButton(text="📊 Статус", payload="act:status"),
    )
    kb.row(CallbackButton(text="🖥️ Дашборд", payload="act:dashboard"))
    kb.row(
        CallbackButton(text="✅ YOLO on", payload="act:yolo:on"),
        CallbackButton(text="⛔ YOLO off", payload="act:yolo:off"),
    )
    kb.row(CallbackButton(text="📋 Контекст", payload="act:context"))
    kb.row(
        CallbackButton(text="🏠 Handoff", payload="act:handoff"),
    )
    kb.row(CallbackButton(text="❓ Справка", payload="act:help"))
    return kb.as_markup()
