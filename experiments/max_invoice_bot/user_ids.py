"""User id namespace: MAX ids are separate from Telegram."""

from __future__ import annotations

PREFIX = "max:"


def store_user_id(max_user_id: int) -> str:
    return f"{PREFIX}{max_user_id}"


def parse_store_user_id(store_id: str) -> int | None:
    if store_id.startswith(PREFIX):
        tail = store_id[len(PREFIX) :]
        if tail.isdigit():
            return int(tail)
    return None


def storage_dir_key(store_key: str) -> str:
    """Filesystem-safe key for pending/split dirs (Windows rejects ':' in paths)."""
    return store_key.replace(":", "_")
