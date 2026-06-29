"""Pluggable state backends for tasks and distributed coordination.

This module addresses C1 (loss of tasks on failover) from the distributed agents review.

Design goals:
- Backward compatible: default behaviour == current DB-only implementation.
- Choice of backend via config (db | redis | hybrid).
- Used by task_store, api, worker, bot manager.
- Easy to extend (add more backends later: postgres-specific, etc).

See docs/governance/DISTRIBUTED_AGENTS_ANALYSIS.md for full rationale and alternatives.
"""

from __future__ import annotations

from typing import Protocol, Any
from datetime import datetime

from app.config import settings


class TaskStateBackend(Protocol):
    """Abstract backend for task state (unified across instances)."""

    def create_task(self, request_id: str, **kwargs: Any) -> None: ...
    def mark_processing(self, request_id: str) -> None: ...
    def mark_done(self, request_id: str, result: dict[str, Any]) -> None: ...
    def mark_error(self, request_id: str, message: str, error: str | None = None) -> None: ...
    def get_task(self, request_id: str) -> dict[str, Any] | None: ...
    def list_user_tasks(self, user_id: str | None, limit: int = 10) -> list[dict[str, Any]]: ...


def get_state_backend() -> TaskStateBackend:
    """Factory. Chooses backend based on settings.state_backend (extensible)."""
    backend = getattr(settings, "state_backend", "db").lower()

    if backend == "redis":
        from app.state.redis_backend import RedisTaskStateBackend
        return RedisTaskStateBackend()
    elif backend in ("db", "sqlite", "postgres"):
        from app.state.db_backend import DBTaskStateBackend
        return DBTaskStateBackend()
    else:
        # Safe default + warning (but we log in caller)
        from app.state.db_backend import DBTaskStateBackend
        return DBTaskStateBackend()


# Convenience re-exports (so callers can stay mostly the same)
from app.state.db_backend import DBTaskStateBackend  # noqa: F401
try:
    from app.state.redis_backend import RedisTaskStateBackend  # noqa: F401
except ImportError:
    RedisTaskStateBackend = None  # type: ignore
