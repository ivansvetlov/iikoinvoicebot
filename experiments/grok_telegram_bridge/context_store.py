"""Per-user conversation context for bridge."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TurnRecord:
    ts: str
    role: str  # user | assistant | system
    text: str
    run_id: str | None = None
    grok_session_id: str | None = None


class ContextStore:
    def __init__(self, base_dir: Path, *, max_turns: int = 40) -> None:
        self._base = base_dir
        self._max = max_turns
        self._lock = threading.Lock()
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self._base / f"{user_id}.jsonl"

    def append(
        self,
        user_id: int,
        *,
        role: str,
        text: str,
        run_id: str | None = None,
        grok_session_id: str | None = None,
    ) -> None:
        rec = TurnRecord(
            ts=datetime.now(timezone.utc).isoformat(),
            role=role,
            text=(text or "").strip(),
            run_id=run_id,
            grok_session_id=grok_session_id,
        )
        line = json.dumps(asdict(rec), ensure_ascii=False)
        with self._lock:
            path = self._path(user_id)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._trim(path)

    def _trim(self, path: Path) -> None:
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self._max:
            return
        path.write_text("\n".join(lines[-self._max :]) + "\n", encoding="utf-8")

    def recent(self, user_id: int, limit: int = 8) -> list[TurnRecord]:
        path = self._path(user_id)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[TurnRecord] = []
        for raw in lines[-limit:]:
            try:
                data = json.loads(raw)
                out.append(TurnRecord(**data))
            except Exception:
                continue
        return out

    def clear(self, user_id: int) -> None:
        with self._lock:
            path = self._path(user_id)
            if path.exists():
                path.unlink()

    def format_preview(self, user_id: int, limit: int = 6) -> str:
        turns = self.recent(user_id, limit=limit)
        if not turns:
            return "Контекст пуст. Отправь задачу текстом."
        lines: list[str] = []
        for t in turns:
            preview = t.text.replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:117] + "…"
            lines.append(f"[{t.role}] {preview}")
        return "\n".join(lines)
