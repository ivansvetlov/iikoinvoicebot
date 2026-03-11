"""RQ worker entrypoint."""

import logging

from rq import SimpleWorker
from rq.timeouts import TimerDeathPenalty

from app.config import settings
from app.observability import configure_logging
from app.queue import get_queue

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    configure_logging("worker")
    queue = get_queue()
    logger.info("Worker ready, listening on queue '%s'", settings.queue_name)
    worker = SimpleWorker([queue], connection=queue.connection)
    worker.death_penalty_class = TimerDeathPenalty
    worker.work(logging_level=settings.log_level.strip().upper())
