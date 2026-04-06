"""RQ worker entrypoint."""

import logging

from rq import SimpleWorker
from rq.timeouts import TimerDeathPenalty

from app.config import settings
from app.observability import configure_logging
from app.queue import get_queue


if __name__ == "__main__":
    configure_logging(
        "worker",
        level=settings.log_level,
        max_bytes=settings.log_max_mb * 1024 * 1024,
        backup_count=settings.log_backup_count,
        archive_after_days=settings.log_archive_after_days,
    )
    logger = logging.getLogger(__name__)
    queue = get_queue()
    logger.info("✅ Worker ready, listening on queue '%s'", settings.queue_name)
    worker = SimpleWorker([queue], connection=queue.connection)
    worker.death_penalty_class = TimerDeathPenalty
    worker.work()
