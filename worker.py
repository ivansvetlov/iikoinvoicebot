"""RQ worker entrypoint."""

from rq import SimpleWorker
from rq.timeouts import TimerDeathPenalty

from app.queue import get_queue


if __name__ == "__main__":
    queue = get_queue()
    print("✅ Worker ready, listening on queue 'default'")
    worker = SimpleWorker([queue], connection=queue.connection)
    worker.death_penalty_class = TimerDeathPenalty
    worker.work()
