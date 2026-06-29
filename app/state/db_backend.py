"""DB-backed task state (current production implementation, extracted for pluggability).

This is the default. Preserves 100% backward compatibility.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.db import get_session, init_db
from app.models import TaskRecord


class DBTaskStateBackend:
    """Exact behaviour of the old task_store.py functions."""

    def __init__(self) -> None:
        init_db()

    def _get_session(self):
        return get_session()

    def create_task(
        self,
        request_id: str,
        filename: str | None = None,
        user_id: str | None = None,
        chat_id: int | None = None,
        batch: bool = False,
        push_to_iiko: bool = True,
        pdf_mode: str | None = None,
    ) -> None:
        with self._get_session() as session:
            if session is None:
                return
            task = TaskRecord(
                request_id=request_id,
                status="queued",
                user_id=user_id,
                chat_id=str(chat_id) if chat_id is not None else None,
                filename=filename,
                batch=batch,
                push_to_iiko=push_to_iiko,
                pdf_mode=pdf_mode,
            )
            session.add(task)

    def mark_processing(self, request_id: str) -> None:
        with self._get_session() as session:
            if session is None:
                return
            task = session.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
            if task:
                task.status = "processing"

    def mark_done(self, request_id: str, result: dict[str, Any]) -> None:
        with self._get_session() as session:
            if session is None:
                return
            task = session.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
            if not task:
                return
            task.status = result.get("status", "done")
            task.iiko_uploaded = result.get("iiko_uploaded")
            task.iiko_error = result.get("iiko_error")
            task.message = result.get("message")
            task.result_json = json.dumps(result, ensure_ascii=False, default=str)
            task.finished_at = datetime.utcnow()

    def mark_error(self, request_id: str, message: str, error: str | None = None) -> None:
        with self._get_session() as session:
            if session is None:
                return
            task = session.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
            if task:
                task.status = "error"
                task.message = message
                task.error = error

    def get_task(self, request_id: str) -> dict[str, Any] | None:
        with self._get_session() as session:
            if session is None:
                return None
            task = session.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
            if not task:
                return None
            return {
                "request_id": task.request_id,
                "status": task.status,
                "user_id": task.user_id,
                "filename": task.filename,
                "iiko_uploaded": task.iiko_uploaded,
                "message": task.message,
                "error": task.error,
                "created_at": task.created_at,
                "finished_at": task.finished_at,
            }

    def list_user_tasks(self, user_id: str | None, limit: int = 10) -> list[dict[str, Any]]:
        with self._get_session() as session:
            if session is None:
                return []
            q = session.query(TaskRecord)
            if user_id:
                q = q.filter(TaskRecord.user_id == user_id)
            tasks = q.order_by(TaskRecord.created_at.desc()).limit(limit).all()
            return [
                {
                    "request_id": t.request_id,
                    "status": t.status,
                    "filename": t.filename,
                    "created_at": t.created_at,
                }
                for t in tasks
            ]
