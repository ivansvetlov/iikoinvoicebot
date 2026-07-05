"""RQ worker entrypoint."""

import logging

from rq import SimpleWorker
from rq.timeouts import TimerDeathPenalty

from app.config import settings
from app.observability import configure_logging
from app.ocr.vpn import ensure_api_vpn
from app.queue import get_queue


def _ensure_recognition_vpn_at_startup(logger: logging.Logger) -> None:
    """Bring up the dev split-tunnel once at worker start (Windows only).

    This is the ONLY place that actively starts the tunnel. The request path
    (pipeline.ensure_recognition_vpn_ok) just checks the state and fails fast.
    On Linux/VPS this is a no-op — the tunnel is a deployment concern there.
    A failed start does not abort the worker: it logs a warning and continues,
    so recognition requests will then surface ``vpn_unavailable`` to the user
    instead of stalling startup.
    """
    if ensure_api_vpn(raise_on_failure=False):
        logger.info("Recognition VPN tunnel is up")
    else:
        logger.warning(
            "Recognition VPN tunnel is NOT up; recognition requests will "
            "fail with vpn_unavailable until the tunnel is started manually"
        )


if __name__ == "__main__":
    configure_logging(
        "worker",
        level=settings.log_level,
        max_bytes=settings.log_max_mb * 1024 * 1024,
        backup_count=settings.log_backup_count,
        archive_after_days=settings.log_archive_after_days,
    )
    logger = logging.getLogger(__name__)
    _ensure_recognition_vpn_at_startup(logger)
    queue = get_queue()
    logger.info("✅ Worker ready, listening on queue '%s'", settings.queue_name)
    worker = SimpleWorker(
        [queue],
        connection=queue.connection,
        default_worker_ttl=settings.worker_ttl_sec,
        maintenance_interval=settings.worker_maintenance_interval_sec,
        job_monitoring_interval=settings.worker_job_monitoring_interval_sec,
    )
    worker.death_penalty_class = TimerDeathPenalty
    worker.work()
