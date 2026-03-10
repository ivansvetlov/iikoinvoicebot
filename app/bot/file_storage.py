"""Вспомогательное хранилище файлов pending/split для Telegram-бота.

Отвечает только за работу с файловой системой:
- где лежат временные файлы пользователя;
- как их сохранить / прочитать / очистить.

Логика Telegram (сообщения, статусы) остаётся в `manager.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


class PendingSplitStorage:
    """Хранилище файлов pending/split на диске."""

    def __init__(self, base_data_dir: Path) -> None:
        self._split_dir = base_data_dir / "split"
        self._pending_dir = base_data_dir / "pending"
        self._split_dir.mkdir(parents=True, exist_ok=True)
        self._pending_dir.mkdir(parents=True, exist_ok=True)

    @property
    def split_dir(self) -> Path:
        return self._split_dir

    @property
    def pending_dir(self) -> Path:
        return self._pending_dir

    def store_split_bytes(self, user_id: str, filename: str, content: bytes) -> None:
        user_dir = self._split_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_name = Path(filename).name
        target = user_dir / f"{stamp}_{safe_name}"
        target.write_bytes(content)

    def store_pending_bytes(self, user_id: str, filename: str, content: bytes) -> None:
        user_dir = self._pending_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_name = Path(filename).name
        target = user_dir / f"{stamp}_{safe_name}"
        target.write_bytes(content)

    def collect_pending_files(self, user_id: str) -> list[tuple[str, bytes]]:
        user_dir = self._pending_dir / user_id
        if not user_dir.exists():
            return []
        files: list[tuple[str, bytes]] = []
        for path in sorted(user_dir.glob("*")):
            if path.is_file():
                files.append((path.name, path.read_bytes()))
        return files

    def clear_pending_dir(self, user_id: str) -> None:
        self._clear_user_dir(self._pending_dir / user_id)

    def collect_split_files(self, user_id: str) -> list[tuple[str, bytes]]:
        user_dir = self._split_dir / user_id
        if not user_dir.exists():
            return []
        files: list[tuple[str, bytes]] = []
        for path in sorted(user_dir.glob("*")):
            if path.is_file():
                files.append((path.name, path.read_bytes()))
        return files

    def clear_split_dir(self, user_id: str) -> None:
        self._clear_user_dir(self._split_dir / user_id)

    def cleanup_old(self, hours: int = 12) -> None:
        """Удаляет старые файлы из pending/split."""
        cutoff = datetime.now() - timedelta(hours=hours)
        for base in (self._pending_dir, self._split_dir):
            if not base.exists():
                continue
            for user_dir in base.iterdir():
                if not user_dir.is_dir():
                    continue
                for item in user_dir.iterdir():
                    try:
                        mtime = datetime.fromtimestamp(item.stat().st_mtime)
                        if mtime < cutoff:
                            item.unlink()
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to cleanup pending/split file")

    @staticmethod
    def _clear_user_dir(path: Path) -> None:
        if not path.exists():
            return
        for item in path.glob("*"):
            if item.is_file():
                try:
                    item.unlink()
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to remove file %s", item)

