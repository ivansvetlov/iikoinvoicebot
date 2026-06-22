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
    kb.row(
        CallbackButton(text="🖥️ Дашборд", payload="act:dashboard"),
        CallbackButton(text="🔄 Обновить HTML", payload="act:dash:refresh"),
    )
    kb.row(
        CallbackButton(text="📜 Логи", payload="act:logs"),
        CallbackButton(text="📈 Метрики", payload="act:metrics"),
        CallbackButton(text="📋 Отчёты", payload="act:reports"),
    )
    kb.row(
        CallbackButton(text="✅ YOLO on", payload="act:yolo:on"),
        CallbackButton(text="⛔ YOLO off", payload="act:yolo:off"),
    )
    kb.row(
        CallbackButton(text="🔍 Проверить (check)", payload="act:check"),
        CallbackButton(text="📋 Контекст", payload="act:context"),
    )
    kb.row(
        CallbackButton(text="🏠 Handoff", payload="act:handoff"),
        CallbackButton(text="📓 Журнал", payload="act:journal"),
    )
    kb.row(CallbackButton(text="❓ Справка", payload="act:help"))
    return kb.as_markup()
