"""Telegram message formatting and chunking."""
from __future__ import annotations

import html
import re

TG_MAX = 4096
TG_SAFE = 4000


def escape_html(text: str) -> str:
    return html.escape(text or "")


def split_message(text: str, limit: int = TG_SAFE) -> list[str]:
    text = (text or "").strip()
    if not text:
        return ["(пустой ответ)"]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return chunks


def progress_preview(text: str, max_len: int = 3500) -> str:
    """Tail of long streaming output for editMessage."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return "…\n" + text[-max_len:]


def wrap_code_block(text: str) -> str:
    safe = escape_html(text)
    return f"<pre>{safe}</pre>"
