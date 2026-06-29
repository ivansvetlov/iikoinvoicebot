"""Redis-backed task state backend.

Alternative for C1 (unified state across failover).

Uses Redis hashes + JSON for task records.
Falls back gracefully if Redis is down (logs warning, returns None/empty).

Advantages over pure DB:
- Atomic operations
- Fast status checks and list queries (for bot UX)
- Easy to add pub/sub for real-time notifications later
- TTL support for auto cleanup of stale data

This backend can be used *in addition* to DB (hybrid) or standalone.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from redis import Redis

from app.config import settings
from app.queue import get_redis  # reuse existing connection helper

logger = logging.getLogger(__name__)

REDIS_TASK_PREFIX = "task:"
REDIS_USER_TASKS = "user_tasks:"  # sorted set per user


class RedisTaskStateBackend:
    """Redis implementation. Stores full record as JSON in hash + indexes."""

    def __init__(self) -> None:
        try:
            self.redis: Redis = get_redis()
            self.redis.ping()
            self._available = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis state backend unavailable: %s. Will be no-op or degraded.", exc)
            self._available = False
            self.redis = None  # type: ignore

    def _key(self, request_id: str) -> str:
        return f"{REDIS_TASK_PREFIX}{request_id}"

    def _user_key(self, user_id: str) -> str:
        return f"{REDIS_USER_TASKS}{user_id or 'anonymous'}"

    def create_task(
        self,
        request_id: str,
        filename: str | None = None,
        user_id: str | None = None,
        chat_id: int | None = None,
        batch: bool = False,
        push_to_iiko: bool = True,
        pdf_mode: str | None = None,
        **_ignored,
    ) -> None:
        if not self._available:
            return

        record = {
            "request_id": request_id,
            "status": "queued",
            "user_id": user_id,
            "chat_id": str(chat_id) if chat_id else None,
            "filename": filename,
            "batch": batch,
            "push_to_iiko": push_to_iiko,
            "pdf_mode": pdf_mode,
            "created_at": datetime.utcnow().isoformat(),
            "finished_at": None,
            "iiko_uploaded": None,
            "message": None,
            "error": None,
            "result_json": None,
        }

        try:
            self.redis.setex(
                self._key(request_id),
                settings.worker_ttl_sec or 1800,
                json.dumps(record, ensure_ascii=False),
            )
            if user_id:
                # Use sorted set for recent user tasks (score = timestamp)
                ts = datetime.utcnow().timestamp()
                self.redis.zadd(self._user_key(user_id), {request_id: ts})
                self.redis.expire(self._user_key(user_id), settings.worker_ttl_sec or 1800)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Redis create_task failed for %s: %s", request_id, exc)

    def mark_processing(self, request_id: str) -> None:
        if not self._available:
            return
        try:
            key = self._key(request_id)
            data = self.redis.get(key)
            if data:
                rec = json.loads(data)
                rec["status"] = "processing"
                self.redis.setex(key, settings.worker_ttl_sec or 1800, json.dumps(rec))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Redis mark_processing failed: %s", exc)

    def mark_done(self, request_id: str, result: dict[str, Any]) -> None:
        if not self._available:
            return
        try:
            key = self._key(request_id)
            data = self.redis.get(key)
            if data:
                rec = json.loads(data)
                rec.update({
                    "status": result.get("status", "done"),
                    "iiko_uploaded": result.get("iiko_uploaded"),
                    "iiko_error": result.get("iiko_error"),
                    "message": result.get("message"),
                    "result_json": json.dumps(result, ensure_ascii=False, default=str),
                    "finished_at": datetime.utcnow().isoformat(),
                })
                self.redis.setex(key, settings.worker_ttl_sec or 1800, json.dumps(rec))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Redis mark_done failed: %s", exc)

    def mark_error(self, request_id: str, message: str, error: str | None = None) -> None:
        if not self._available:
            return
        try:
            key = self._key(request_id)
            data = self.redis.get(key)
            if data:
                rec = json.loads(data)
                rec["status"] = "error"
                rec["message"] = message
                rec["error"] = error
                rec["finished_at"] = datetime.utcnow().isoformat()
                self.redis.setex(key, settings.worker_ttl_sec or 1800, json.dumps(rec))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Redis mark_error failed: %s", exc)

    def get_task(self, request_id: str) -> dict[str, Any] | None:
        if not self._available:
            return None
        try:
            data = self.redis.get(self._key(request_id))
            return json.loads(data) if data else None
        except Exception as exc:  # noqa: BLE001
            logger.exception("Redis get_task failed: %s", exc)
            return None

    def list_user_tasks(self, user_id: str | None, limit: int = 10) -> list[dict[str, Any]]:
        if not self._available or not user_id:
            return []
        try:
            user_key = self._user_key(user_id)
            # Get most recent request_ids
            ids = self.redis.zrevrange(user_key, 0, limit - 1)
            results = []
            for rid in ids:
                rid_str = rid.decode() if isinstance(rid, bytes) else rid
                data = self.redis.get(self._key(rid_str))
                if data:
                    rec = json.loads(data)
                    results.append({
                        "request_id": rec.get("request_id"),
                        "status": rec.get("status"),
                        "filename": rec.get("filename"),
                        "created_at": rec.get("created_at"),
                    })
            return results
        except Exception as exc:  # noqa: BLE001
            logger.exception("Redis list_user_tasks failed: %s", exc)
            return []
