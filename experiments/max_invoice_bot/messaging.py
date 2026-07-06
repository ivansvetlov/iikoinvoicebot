"""Send/edit/split messages in MAX."""
from __future__ import annotations

import asyncio
from typing import Any

from maxapi import Bot
from maxapi.enums.parse_mode import ParseMode
from maxapi.types.message import Message
from maxapi.types.updates import MessageCallback

from experiments.max_invoice_bot.keyboards import dict_to_markup

MAX_API_TEXT_LIMIT = 4000
TEXT_LIMIT = 3900
HTML = ParseMode.HTML


def prepare_outgoing_text(text: str, *, limit: int = TEXT_LIMIT) -> str:
    """Keep a single MAX message within API text limits."""
    return split_text(text, limit=limit)[0]


def split_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return chunks


def keyboard_to_edit_attachments(keyboard: dict[str, Any] | None) -> list[Any]:
    """MAX edit/callback: None keyboard clears inline buttons; dict replaces them."""
    markup = dict_to_markup(keyboard)
    return [] if markup is None else markup


async def send_to_user(
    bot: Bot,
    *,
    chat_id: int | None,
    user_id: int,
    text: str,
    keyboard: dict[str, Any] | None = None,
) -> Message | None:
    attachments = dict_to_markup(keyboard)
    chunks = split_text(text)
    sent = None
    for i, chunk in enumerate(chunks):
        kw = {"format": HTML}
        if i == 0 and attachments:
            kw["attachments"] = attachments
        sent = await bot.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=chunk,
            **kw,
        )
        if i < len(chunks) - 1:
            await asyncio.sleep(0.25)
    return sent


async def edit_message(
    message: Message,
    text: str,
    keyboard: dict[str, Any] | None = None,
) -> None:
    attachments = keyboard_to_edit_attachments(keyboard)
    await message.edit(
        text=prepare_outgoing_text(text),
        attachments=attachments,
        format=HTML,
    )


async def dismiss_message(message: Message, *, text: str = " ") -> None:
    """Blank a message and remove inline keyboard (prevents floating buttons)."""
    await edit_message(message, text, keyboard=None)


async def reply_or_edit(
    message: Message,
    text: str,
    keyboard: dict[str, Any] | None = None,
) -> Message:
    try:
        await edit_message(message, text, keyboard)
        return message
    except Exception:
        bot = message.bot
        if bot is None:
            raise
        uid = message.sender.user_id if message.sender else 0
        chat_id = message.recipient.chat_id if message.recipient else None
        sent = await send_to_user(
            bot,
            chat_id=chat_id,
            user_id=uid,
            text=text,
            keyboard=keyboard,
        )
        return sent or message


async def callback_update(
    event: MessageCallback,
    text: str,
    keyboard: dict[str, Any] | None = None,
) -> None:
    attachments = keyboard_to_edit_attachments(keyboard)
    await event.answer(
        new_text=prepare_outgoing_text(text),
        attachments=attachments,
        format=HTML,
    )
