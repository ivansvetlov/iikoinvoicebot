"""Telegram inline keyboards for bridge bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆕 Новая сессия", callback_data="act:new"),
                InlineKeyboardButton(text="📊 Статус", callback_data="act:status"),
            ],
            [
                InlineKeyboardButton(text="🖥️ Дашборд", callback_data="act:dashboard"),
            ],
            [
                InlineKeyboardButton(text="✅ YOLO on", callback_data="act:yolo:on"),
                InlineKeyboardButton(text="⛔ YOLO off", callback_data="act:yolo:off"),
            ],
            [
                InlineKeyboardButton(text="📋 Контекст", callback_data="act:context"),
            ],
            [
                InlineKeyboardButton(text="🏠 Handoff", callback_data="act:handoff"),
            ],
            [
                InlineKeyboardButton(text="❓ Справка", callback_data="act:help"),
            ],
        ]
    )
