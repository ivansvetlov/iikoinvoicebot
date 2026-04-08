"""Хранилище задач обработки (Postgres/SQLite)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func

from app.db import get_session, init_db
from app.models import TaskRecord


def create_task(
    request_id: str,
    filename: str | None,
    user_id: str | None,
    chat_id: int | None,
    batch: bool,
    push_to_iiko: bool,
    pdf_mode: str | None,
) -> None:
    init_db()
    with get_session() as session:
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


def mark_processing(request_id: str) -> None:
    init_db()
    with get_session() as session:
        if session is None:
            return
        task = session.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
        if not task:
            return
        task.status = "processing"


def mark_done(request_id: str, result: dict[str, Any]) -> None:
    init_db()
    with get_session() as session:
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


def mark_error(request_id: str, message: str, error: str | None = None) -> None:
    init_db()
    with get_session() as session:
        if session is None:
            return
        task = session.query(TaskRecord).filter(TaskRecord.request_id == request_id).one_or_none()
        if not task:
            return
        task.status = "error"
        task.message = message
        task.error = error
        task.finished_at = datetime.utcnow()


def get_queue_snapshot() -> dict[str, int]:
    """Возвращает агрегаты по очереди задач."""
    init_db()
    with get_session() as session:
        if session is None:
            return {"queued": 0, "processing": 0}
        rows = (
            session.query(TaskRecord.status, func.count(TaskRecord.id))
            .filter(TaskRecord.status.in_(("queued", "processing")))
            .group_by(TaskRecord.status)
            .all()
        )
        snapshot = {"queued": 0, "processing": 0}
        for status, count in rows:
            snapshot[str(status)] = int(count)
        return snapshot


def get_user_active_snapshot(user_id: str, *, active_hours: int, stale_minutes: int) -> dict[str, int]:
    """Возвращает активные счетчики задач пользователя в заданном окне."""
    init_db()
    with get_session() as session:
        if session is None:
            return {"queued": 0, "processing": 0, "stale": 0}
        active_cutoff = datetime.utcnow().timestamp() - (active_hours * 3600)
        stale_cutoff = datetime.utcnow().timestamp() - (stale_minutes * 60)

        tasks = (
            session.query(TaskRecord)
            .filter(TaskRecord.user_id == user_id)
            .filter(TaskRecord.status.in_(("queued", "processing")))
            .all()
        )

        snapshot = {"queued": 0, "processing": 0, "stale": 0}
        for task in tasks:
            created_at = task.created_at
            if not created_at:
                continue
            if created_at.timestamp() < active_cutoff:
                continue

            status = str(task.status or "")
            if status in ("queued", "processing"):
                snapshot[status] += 1

            touch_ts = (task.updated_at or task.created_at).timestamp()
            if touch_ts < stale_cutoff:
                snapshot["stale"] += 1
        return snapshot


def get_user_last_task(user_id: str) -> dict[str, Any] | None:
    """Возвращает последнюю задачу пользователя."""
    init_db()
    with get_session() as session:
        if session is None:
            return None
        task = (
            session.query(TaskRecord)
            .filter(TaskRecord.user_id == user_id)
            .order_by(TaskRecord.created_at.desc(), TaskRecord.id.desc())
            .first()
        )
        if not task:
            return None
        return {
            "request_id": task.request_id,
            "status": task.status,
            "message": task.message,
            "batch": bool(task.batch),
            "created_at": task.created_at,
            "finished_at": task.finished_at,
        }
