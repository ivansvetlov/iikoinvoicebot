"""Очередь задач и подключение к Redis."""

from redis import Redis
from rq import Queue

from app.config import settings


def get_redis() -> Redis:
    """Создает подключение к Redis."""
    return Redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    """Возвращает очередь задач."""
    return Queue(settings.queue_name, connection=get_redis())
