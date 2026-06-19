"""Tester / verifier integration (Grok --check, same as /check-work skill)."""
from __future__ import annotations

import re

# User explicitly asks for verification
CHECK_PATTERNS = re.compile(
    r"(?i)(/check\b|/verify\b|проверь|верифицируй|check work|self-verify)",
)

# Likely code-change prompts — optional auto-check when enabled in settings
CODE_PATTERNS = re.compile(
    r"(?i)\b(implement|fix|refactor|добавь|исправь|сделай|напиши|commit|patch|bug)\b",
)


def should_use_check(prompt: str, *, auto_check: bool) -> bool:
    if CHECK_PATTERNS.search(prompt):
        return True
    if auto_check and CODE_PATTERNS.search(prompt):
        return True
    return False


def strip_check_prefix(prompt: str) -> str:
    return re.sub(r"(?i)^/(check|verify)\s*", "", prompt.strip()).strip() or prompt
