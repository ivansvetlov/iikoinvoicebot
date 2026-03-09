"""Хранилище задач обработки (Postgres/SQLite)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

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
