"""Access control for the bridge bot."""
from __future__ import annotations


def is_allowed(user_id: int, allowed: set[int]) -> bool:
    if not allowed:
        return False
    return user_id in allowed
