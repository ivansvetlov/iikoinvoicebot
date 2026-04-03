"""RQ queue setup and job policy helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx
from redis import Redis
from rq import Queue, Retry
from rq.job import Job

from app.config import settings
from app.observability import append_metric
from app.task_store import mark_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueueJobPolicy:
    profile: str
    job_timeout: int
    retry_max: int
    retry_intervals: list[int]
    result_ttl: int
    failure_ttl: int


def get_redis() -> Redis:
    """Create Redis connection."""
    return Redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    """Return RQ queue instance."""
    return Queue(settings.queue_name, connection=get_redis())


def _parse_retry_intervals(raw: str) -> list[int]:
    values: list[int] = []
    for token in str(raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError:
            continue
        if value > 0:
            values.append(value)
    return values or [30, 120, 300]


def _build_retry_intervals(max_retries: int) -> list[int]:
    if max_retries <= 0:
        return []
    base = _parse_retry_intervals(settings.queue_retry_intervals_sec)
    if len(base) >= max_retries:
        return base[:max_retries]
    if not base:
        return [30] * max_retries
    tail = base[-1]
    return base + [tail] * (max_retries - len(base))


def build_invoice_job_policy(*, batch: bool, push_to_iiko: bool) -> QueueJobPolicy:
    if push_to_iiko:
        profile = "iiko"
        timeout = max(1, settings.queue_timeout_iiko_sec)
        retry_max = max(0, settings.queue_retry_iiko_max)
    elif batch:
        profile = "batch"
        timeout = max(1, settings.queue_timeout_batch_sec)
        retry_max = max(0, settings.queue_retry_batch_max)
    else:
        profile = "single"
        timeout = max(1, settings.queue_timeout_single_sec)
        retry_max = max(0, settings.queue_retry_single_max)

    return QueueJobPolicy(
        profile=profile,
        job_timeout=timeout,
        retry_max=retry_max,
        retry_intervals=_build_retry_intervals(retry_max),
        result_ttl=max(1, settings.queue_result_ttl_sec),
        failure_ttl=max(1, settings.queue_failure_ttl_sec),
    )


def _extract_payload(job: Job) -> dict[str, Any]:
    if not job.args:
        return {}
    payload_path = job.args[0]
    if not isinstance(payload_path, str):
        return {}
    path = Path(payload_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _notify_user_job_failed(chat_id: int | None, request_id: str | None) -> None:
    if not chat_id or not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    text = "Не удалось обработать задачу в очереди после нескольких попыток. Попробуйте отправить файл снова."
    if request_id:
        text += f"\nКод заявки: {request_id}"
    try:
        httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception:
        return


def on_invoice_job_failed(
    job: Job,
    connection: Redis,  # noqa: ARG001 - RQ callback signature
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    traceback: str | None,  # noqa: ARG001 - useful for rq internals, we log compactly
) -> None:
    payload = _extract_payload(job)
    request_id = payload.get("request_id")
    chat_id_raw = payload.get("chat_id")
    chat_id = int(chat_id_raw) if isinstance(chat_id_raw, int) else None

    exc_name = exc_type.__name__ if exc_type else "UnknownError"
    exc_text = str(exc_value) if exc_value else "No exception value"
    detail = f"{exc_name}: {exc_text}"
    message = "Задача завершилась ошибкой после исчерпания повторных попыток."

    if request_id:
        mark_error(request_id, message, detail)
    _notify_user_job_failed(chat_id, request_id)

    logger.error(
        "RQ job failed after retries",
        extra={
            "event_code": "WORKER_JOB_FAILED",
            "request_id": request_id,
            "job_id": job.id,
            "queue": settings.queue_name,
            "error": detail,
        },
    )
    append_metric(
        "worker.task.failed",
        status="error",
        request_id=request_id,
        queue=settings.queue_name,
        job_id=job.id,
        error_code="job_failed",
        exception_type=exc_name,
    )


def enqueue_invoice_task(
    *,
    task_func: Callable[..., Any],
    payload_path: str,
    batch: bool,
    push_to_iiko: bool,
) -> Job:
    queue = get_queue()
    policy = build_invoice_job_policy(batch=batch, push_to_iiko=push_to_iiko)
    retry = Retry(max=policy.retry_max, interval=policy.retry_intervals) if policy.retry_max > 0 else None

    enqueue_kwargs: dict[str, Any] = {
        "job_timeout": policy.job_timeout,
        "result_ttl": policy.result_ttl,
        "failure_ttl": policy.failure_ttl,
        "on_failure": on_invoice_job_failed,
        "meta": {"policy_profile": policy.profile},
    }
    if retry is not None:
        enqueue_kwargs["retry"] = retry
    return queue.enqueue(task_func, payload_path, **enqueue_kwargs)

