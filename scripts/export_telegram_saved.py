"""Export Telegram Saved Messages (Избранное) for offline analysis.

Requires a Telegram *user* API app (not bot token):
  https://my.telegram.org/apps

First run (interactive login):
  .\\.venv\\Scripts\\python.exe scripts\\export_telegram_saved.py

Outputs (gitignored via data/):
  data/private/telegram_favorites/messages.jsonl
  data/private/telegram_favorites/messages.json
  data/private/telegram_favorites/links.txt
  data/private/telegram_favorites/export_meta.json

Session file:
  data/private/telegram_user/session.session
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from telethon import TelegramClient
    from telethon.tl.custom.message import Message
except ImportError as exc:  # pragma: no cover
    print(
        "Telethon is required. Install:\n"
        "  .\\.venv\\Scripts\\pip.exe install telethon",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

from app.config import settings

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "private" / "telegram_favorites"
DEFAULT_SESSION_DIR = PROJECT_ROOT / "data" / "private" / "telegram_user"
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.isdigit():
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _entity_label(entity: Any) -> str | None:
    if entity is None:
        return None
    for attr in ("title", "username", "first_name", "last_name"):
        part = getattr(entity, attr, None)
        if part:
            return str(part)
    return str(getattr(entity, "id", None) or "")


def _extract_links(text: str | None, entities: list[Any] | None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        url = url.strip().rstrip(").,;]")
        if not url or url in seen:
            return
        seen.add(url)
        found.append(url)

    if text:
        for match in URL_RE.findall(text):
            add(match)

    for entity in entities or []:
        cls = entity.__class__.__name__.lower()
        if "texturl" in cls:
            add(getattr(entity, "url", "") or "")
        elif "url" in cls and text:
            offset = int(getattr(entity, "offset", 0) or 0)
            length = int(getattr(entity, "length", 0) or 0)
            add(text[offset : offset + length])

    return found


def _message_record(message: Message) -> dict[str, Any]:
    text = message.message or message.text or ""
    entities = list(message.entities or [])
    links = _extract_links(text, entities)

    forward_from = None
    if message.forward:
        forward_from = {
            "from_name": message.forward.sender_name,
            "from_id": getattr(message.forward.from_id, "user_id", None)
            if message.forward.from_id
            else None,
            "channel_id": getattr(message.forward.from_id, "channel_id", None)
            if message.forward.from_id
            else None,
            "date": _iso(message.forward.date),
        }

    return {
        "id": message.id,
        "date": _iso(message.date),
        "text": text,
        "raw_text": text,
        "links": links,
        "has_media": bool(message.media),
        "media_type": message.media.__class__.__name__ if message.media else None,
        "is_forward": bool(message.forward),
        "forward_from": forward_from,
        "reply_to_msg_id": message.reply_to.reply_to_msg_id if message.reply_to else None,
        "grouped_id": message.grouped_id,
        "views": message.views,
        "sender_id": message.sender_id,
    }


async def _export(args: argparse.Namespace) -> int:
    api_id = settings.telegram_api_id
    api_hash = (settings.telegram_api_hash or "").strip()
    if not api_id or not api_hash:
        print(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env\n"
            "Create app: https://my.telegram.org/apps",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output_dir)
    session_dir = Path(args.session_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    session_path = session_dir / "session"
    client = TelegramClient(str(session_path), api_id, api_hash)

    since_dt = _parse_since(args.since)
    limit = int(args.limit or 0) or None

    records: list[dict[str, Any]] = []
    all_links: list[str] = []
    link_seen: set[str] = set()

    await client.start(phone=args.phone)
    try:
        async for message in client.iter_messages("me", limit=limit, reverse=False):
            if since_dt and message.date:
                msg_dt = message.date
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                if msg_dt.astimezone(timezone.utc) < since_dt:
                    break
            if not isinstance(message, Message):
                continue
            record = _message_record(message)
            records.append(record)
            for link in record["links"]:
                if link not in link_seen:
                    link_seen.add(link)
                    all_links.append(link)
    finally:
        await client.disconnect()

    records.sort(key=lambda row: row.get("date") or "", reverse=True)

    jsonl_path = output_dir / "messages.jsonl"
    json_path = output_dir / "messages.json"
    links_path = output_dir / "links.txt"
    meta_path = output_dir / "export_meta.json"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    links_path.write_text("\n".join(all_links) + ("\n" if all_links else ""), encoding="utf-8")

    domains: dict[str, int] = {}
    for link in all_links:
        host = urlparse(link).netloc.lower()
        if host:
            domains[host] = domains.get(host, 0) + 1

    meta = {
        "exported_at": _iso(datetime.now(timezone.utc)),
        "message_count": len(records),
        "link_count": len(all_links),
        "top_domains": sorted(domains.items(), key=lambda item: item[1], reverse=True)[:20],
        "since": _iso(since_dt),
        "limit": limit,
        "output_dir": str(output_dir),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Exported messages: {len(records)}")
    print(f"Unique links: {len(all_links)}")
    print(f"JSONL: {jsonl_path}")
    print(f"JSON:  {json_path}")
    print(f"Links: {links_path}")
    print(f"Meta:  {meta_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Telegram Saved Messages (Избранное).")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for export files (default: data/private/telegram_favorites)",
    )
    parser.add_argument(
        "--session-dir",
        default=str(DEFAULT_SESSION_DIR),
        help="Directory for Telethon session (default: data/private/telegram_user)",
    )
    parser.add_argument(
        "--phone",
        default=None,
        help="Phone number for first login (+7999...). Prompted if omitted.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Export only messages newer than ISO date or unix timestamp",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max messages to scan from newest (0 = all)",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_export(args))


if __name__ == "__main__":
    raise SystemExit(main())
