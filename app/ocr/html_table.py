"""Normalize SotaOCR HTML table output into plain text for InvoiceParser."""
from __future__ import annotations

import re


_TAG_RE = re.compile(r"<[^>]+>")


def html_tables_to_text(raw: str) -> str:
    """Convert HTML tables to tab-separated lines suitable for fast parser."""
    if not raw or "<table" not in raw.lower():
        return raw

    text = raw.replace("</tr>", "\n").replace("<tr>", "")
    text = _TAG_RE.sub("\t", text)
    lines: list[str] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.split("\t") if cell.strip()]
        if cells:
            lines.append("\t".join(cells))
    return "\n".join(lines)
