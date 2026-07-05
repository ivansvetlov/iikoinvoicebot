"""Download user attachments from MAX messages."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from maxapi.enums.attachment import AttachmentType
from maxapi.types.message import Message

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DownloadedFile:
    filename: str
    content: bytes
    mime_hint: str | None = None


def _url_from_payload(payload) -> str | None:
    if payload is None:
        return None
    url = getattr(payload, "url", None)
    if url:
        return str(url)
    return None


def _iter_file_attachments(message: Message):
    """Attachments from message body and from forwarded/replied linked message."""
    bodies = []
    if message.body:
        bodies.append(message.body)
    link = message.link
    if link and link.message:
        bodies.append(link.message)
    for body in bodies:
        for att in body.attachments or []:
            atype = getattr(att, "type", None)
            if atype in (AttachmentType.FILE, AttachmentType.IMAGE):
                yield att


def has_downloadable_attachments(message: Message) -> bool:
    return next(_iter_file_attachments(message), None) is not None


async def download_from_message(message: Message, *, auth_token: str) -> list[DownloadedFile]:
    attachments = list(_iter_file_attachments(message))
    if not attachments:
        return []
    headers = {"Authorization": auth_token}
    results: list[DownloadedFile] = []
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        for att in attachments:
            atype = getattr(att, "type", None)
            if atype == AttachmentType.INLINE_KEYBOARD:
                continue
            if atype not in (AttachmentType.FILE, AttachmentType.IMAGE):
                logger.info("Skipping unsupported attachment type: %s", atype)
                continue
            filename = getattr(att, "filename", None) if atype == AttachmentType.FILE else "invoice_photo.jpg"
            filename = filename or ("invoice_photo.jpg" if atype == AttachmentType.IMAGE else "invoice.bin")
            url = _url_from_payload(getattr(att, "payload", None))
            if not url:
                logger.warning("Attachment without url: %s", atype)
                continue
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                results.append(DownloadedFile(filename=filename, content=resp.content))
            except Exception:
                logger.exception("Failed to download %s", filename)
    return results
