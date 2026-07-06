"""Хранилище задач обработки — тонкая фасадная обёртка над pluggable backend.

Обратная совместимость: все публичные функции сохранены 1:1.
Реальное хранение теперь делегируется в app/state/ (см. docs/governance/DISTRIBUTED_AGENTS_ANALYSIS.md).

Поддерживаемые бэкенды (STATE_BACKEND в .env):
- "db" (по умолчанию) — текущая SQLite/Postgres логика
- "redis" — распределённое состояние через Redis (рекомендуется для failover)
"""

from __future__ import annotations

from typing import Any

from app.state import get_state_backend

# Keep the constant for compatibility with callers
STALE_TASK_MESSAGE = "Заявка не завершилась вовремя. Отправьте файл повторно."

# Singleton backend (lazy)
_state_backend = None


def _get_backend():
    global _state_backend
    if _state_backend is None:
        _state_backend = get_state_backend()
    return _state_backend


def create_task(
    request_id: str,
    filename: str | None,
    user_id: str | None,
    chat_id: int | None,
    batch: bool,
    push_to_iiko: bool,
    pdf_mode: str | None,
) -> None:
    _get_backend().create_task(
        request_id=request_id,
        filename=filename,
        user_id=user_id,
        chat_id=chat_id,
        batch=batch,
        push_to_iiko=push_to_iiko,
        pdf_mode=pdf_mode,
    )


def mark_processing(request_id: str) -> None:
    _get_backend().mark_processing(request_id)


def mark_done(request_id: str, result: dict[str, Any]) -> None:
    _get_backend().mark_done(request_id, result)


def mark_error(request_id: str, message: str, error: str | None = None) -> None:
    _get_backend().mark_error(request_id, message, error)


def set_task_progress(request_id: str, message: str) -> None:
    """Update in-flight status line (MAX task_watcher reads task.message)."""
    backend = _get_backend()
    setter = getattr(backend, "set_task_progress", None)
    if callable(setter):
        setter(request_id, message)


# Bonus helpers (non-breaking additions)
def get_task(request_id: str) -> dict[str, Any] | None:
    return _get_backend().get_task(request_id)


def get_user_active_snapshot(user_id: str | None) -> list[dict[str, Any]]:
    """Used by bot/manager.py. Returns recent tasks for user."""
    return _get_backend().list_user_tasks(user_id, limit=5)


def get_user_last_task(user_id: str | None) -> dict[str, Any] | None:
    tasks = _get_backend().list_user_tasks(user_id, limit=1)
    return tasks[0] if tasks else None


def reap_stale_tasks(hours: int = 24) -> int:
    """Placeholder. Real sweep can be implemented per-backend."""
    return 0


def get_queue_snapshot() -> dict[str, int]:
    """Возвращает агрегаты по очереди задач (legacy DB path kept for now)."""
    # For simplicity in transition, delegate to DB directly for snapshot
    from app.db import get_session, init_db
    from sqlalchemy import func
    from app.models import TaskRecord

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


def reap_stale_tasks(*, stale_minutes: int, user_id: str | None = None) -> int:
    """Помечает старые queued/processing задачи как timeout-error и возвращает их количество."""
    init_db()
    with get_session() as session:
        if session is None:
            return 0

        query = session.query(TaskRecord).filter(TaskRecord.status.in_(("queued", "processing")))
        if user_id is not None:
            query = query.filter(TaskRecord.user_id == user_id)
        tasks = query.all()
        if not tasks:
            return 0

        cutoff = datetime.utcnow() - timedelta(minutes=max(stale_minutes, 1))
        now = datetime.utcnow()
        touched = 0
        for task in tasks:
            touch = task.updated_at or task.created_at
            if touch is None or touch >= cutoff:
                continue
            task.status = "error"
            if not (task.message or "").strip():
                task.message = STALE_TASK_MESSAGE
            task.error = "timeout_stale_task"
            task.finished_at = now
            touched += 1
        return touched
