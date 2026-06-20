"""Persist Grok sessionId per Telegram user."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class UserSession:
    user_id: int
    grok_session_id: str | None = None
    yolo: bool | None = None
    last_prompt_at: str | None = None
    message_count: int = 0
    meta: dict = field(default_factory=dict)


class SessionStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict[str, dict]) -> None:
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, user_id: int) -> UserSession:
        with self._lock:
            raw = self._load().get(str(user_id), {})
        return UserSession(user_id=user_id, **{k: v for k, v in raw.items() if k != "user_id"})

    def update(self, session: UserSession) -> None:
        with self._lock:
            data = self._load()
            data[str(session.user_id)] = asdict(session)
            self._save(data)

    def clear(self, user_id: int) -> None:
        with self._lock:
            data = self._load()
            data.pop(str(user_id), None)
            self._save(data)

    def touch_prompt(
        self,
        user_id: int,
        grok_session_id: str | None,
        *,
        meta: dict | None = None,
    ) -> UserSession:
        sess = self.get(user_id)
        sess.grok_session_id = grok_session_id
        sess.message_count += 1
        sess.last_prompt_at = datetime.now(timezone.utc).isoformat()
        if meta is not None:
            sess.meta = meta
        self.update(sess)
        return sess
