"""Load metaprompt / rules for Grok --rules."""
from __future__ import annotations

from pathlib import Path


def load_rules_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None
