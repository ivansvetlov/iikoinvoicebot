"""Persistent idempotency registry for iiko imports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class IikoImportIdempotencyStore:
    """Stores processed external keys to prevent duplicate imports."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def exists(self, external_key: str) -> bool:
        if not external_key or not self._path.exists():
            return False
        with self._lock:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("external_key") == external_key:
                    return True
        return False

    def record(
        self,
        *,
        external_key: str,
        request_id: str,
        mode: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if not external_key:
            return
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "external_key": external_key,
            "request_id": request_id,
            "mode": mode,
            "details": details or {},
        }
        payload = json.dumps(row, ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(payload)
                handle.write("\n")
