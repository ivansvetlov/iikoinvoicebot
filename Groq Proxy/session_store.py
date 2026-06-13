"""Map Kilo conversation threads to grok-cli session IDs for --resume."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from paths import log_path

_DEFAULT_TTL_S = 24 * 3600


def _env_flag(name: str, default: str = "0") -> bool:
    return (os.environ.get(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resume_sessions_enabled() -> bool:
    return _env_flag("GROK_RESUME_SESSIONS", "0")


class GrokSessionStore:
    """Thread-safe Kilo conversation key → grok sessionId map."""

    def __init__(self, *, ttl_s: int | None = None, persist_path: str | None = None) -> None:
        self._ttl_s = ttl_s if ttl_s is not None else _DEFAULT_TTL_S
        self._persist_path = persist_path or os.environ.get("GROK_SESSION_STORE_PATH") or log_path(
            "grok_sessions.json"
        )
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._load()

    def get(self, conversation_key: str) -> str | None:
        if not conversation_key:
            return None
        now = time.time()
        with self._lock:
            entry = self._entries.get(conversation_key)
            if not entry:
                return None
            if now - float(entry.get("updated_at", 0)) > self._ttl_s:
                self._entries.pop(conversation_key, None)
                self._save_locked()
                return None
            sid = entry.get("session_id")
            return sid if isinstance(sid, str) and sid.strip() else None

    def set(self, conversation_key: str, session_id: str) -> None:
        if not conversation_key or not session_id:
            return
        now = time.time()
        with self._lock:
            self._entries[conversation_key] = {
                "session_id": session_id,
                "updated_at": now,
            }
            self._save_locked()

    def clear(self, conversation_key: str) -> None:
        if not conversation_key:
            return
        with self._lock:
            if conversation_key in self._entries:
                self._entries.pop(conversation_key, None)
                self._save_locked()

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def _load(self) -> None:
        path = self._persist_path
        if not path or not os.path.isfile(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._entries = {
                    k: v for k, v in data.items() if isinstance(v, dict) and v.get("session_id")
                }
        except (OSError, json.JSONDecodeError, TypeError):
            self._entries = {}

    def _save_locked(self) -> None:
        path = self._persist_path
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


_STORE: GrokSessionStore | None = None
_STORE_LOCK = threading.Lock()


def get_session_store() -> GrokSessionStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = GrokSessionStore()
        return _STORE
