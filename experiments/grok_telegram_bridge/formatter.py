"""Telegram message formatting and chunking."""
from __future__ import annotations

import html
import re

TG_MAX = 4096
TG_SAFE = 4000
MAX_MSG = 4000
MAX_RAW_CHUNK = 3200


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




def clamp_message(text: str, limit: int = MAX_MSG) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def wrap_code_block_for_max(text: str) -> str:
    """Wrap in <pre> and keep total HTML within MAX API limit (4000 chars)."""
    for raw_limit in (MAX_RAW_CHUNK, 2600, 2000, 1400, 900):
        wrapped = wrap_code_block(split_message(text, limit=raw_limit)[0])
        if len(wrapped) <= MAX_MSG:
            return wrapped
    return clamp_message(wrap_code_block(split_message(text, limit=600)[0]))


def format_grok_for_max(text: str) -> str:
    """Pass Grok markdown through for MAX ``format=markdown`` (native **bold**)."""
    text = (text or "").strip()
    return text or "(пустой ответ)"


def format_grok_response(text: str) -> str:
    """Convert Grok output (with Markdown like **bold**) to Telegram HTML.

    - **bold** and *italic* / _italic_ become <b>/<i>
    - `inline` becomes <code>
    - ``` fenced blocks become <pre><code> (whitespace preserved)
    Everything is HTML-escaped safely.
    """
    if not text or not text.strip():
        return "(пустой ответ)"

    # Capture fenced code blocks (```...```) before any escaping
    fenced: list[tuple[str, str]] = []

    def _replace_fenced(m: re.Match[str]) -> str:
        lang = (m.group(1) or "").strip()
        code = m.group(2) or ""
        idx = len(fenced)
        fenced.append((lang, code))
        return f"\n<<TGFC{idx}>>\n"

    processed = re.sub(r"```(\w+)?\s*\n?([\s\S]*?)\n?```", _replace_fenced, text)

    # Escape remaining text (this will turn <<TGFC0>> into &lt;&lt;TGFC0&gt;&gt;)
    escaped = html.escape(processed)

    # Apply inline Markdown → HTML tags (on escaped text)
    # Bold **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)
    # Italic *text* (avoid double stars)
    escaped = re.sub(r"(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", escaped)
    # Italic _text_
    escaped = re.sub(r"(?<!_)_(?!_)([^_]+?)(?<!_)_(?!_)", r"<i>\1</i>", escaped)
    # Inline code `text`
    escaped = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", escaped)

    # Restore fenced: replace the *escaped* placeholder with <pre> block
    for i, (lang, code) in enumerate(fenced):
        safe = html.escape(code.strip("\n"))
        block = f"<pre>{safe}</pre>"
        placeholder_esc = html.escape(f"<<TGFC{i}>>")
        escaped = escaped.replace(placeholder_esc, block)

    return escaped.strip()
