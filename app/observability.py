"""Единые утилиты наблюдаемости: логирование, алерты, метрики, архив логов."""

from __future__ import annotations

import csv
import gzip
import json
import logging
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
ALERTS_LOG = LOGS_DIR / "alerts.jsonl"
ALERTS_CSV = LOGS_DIR / "alerts.csv"
METRICS_LOG = LOGS_DIR / "metrics.jsonl"
METRICS_CSV = LOGS_DIR / "metrics.csv"
ARCHIVE_DIR = LOGS_DIR / "archive"

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
ALERTS_CSV_HEADER = [
    "ts",
    "component",
    "level",
    "logger",
    "message",
    "event_code",
    "event_short",
    "request_id",
    "extra_json",
]
METRICS_CSV_HEADER = [
    "ts",
    "event",
    "component",
    "status",
    "error_code",
    "status_code",
    "duration_ms",
    "request_id",
    "user_id",
    "path",
    "method",
    "batch",
    "error_type",
    "extra_json",
]


class AlertFileHandler(logging.Handler):
    """Пишет ошибки уровня ERROR+ в отдельный JSONL для алертинга."""

    def __init__(self, component: str) -> None:
        super().__init__(level=logging.ERROR)
        self._component = component

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "component": self._component,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "event_code": getattr(record, "event_code", None),
            "event_short": getattr(record, "event_short", None),
            "request_id": getattr(record, "request_id", None),
        }
        try:
            ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with ALERTS_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False))
                handle.write("\n")
            _append_csv_row(ALERTS_CSV, ALERTS_CSV_HEADER, payload)
        except Exception:
            # Не падаем из-за проблем с вторичным логом.
            return


def configure_logging(
    component: str,
    *,
    level: str | int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
    archive_after_days: int | None = None,
) -> logging.Logger:
    """Настраивает единое логирование процесса (stdout + component.log + alerts)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    marker = f"_invoice_logging_{component}"
    if getattr(root, marker, False):
        return logging.getLogger(component)

    # Очистка предыдущих хендлеров защищает от дублей при повторном импорте.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_DEFAULT_FORMAT)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        LOGS_DIR / f"{component}.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    alert_handler = AlertFileHandler(component=component)

    root.addHandler(stream_handler)
    root.addHandler(file_handler)
    root.addHandler(alert_handler)

    if isinstance(level, str):
        level_value = getattr(logging, level.upper(), logging.INFO)
    else:
        level_value = int(level)
    root.setLevel(level_value)

    if archive_after_days:
        archive_logs(older_than_days=archive_after_days)

    setattr(root, marker, True)
    return logging.getLogger(component)


def track_metric(event: str, **fields: Any) -> None:
    """Записывает метрику в JSONL (`logs/metrics.jsonl`)."""
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **fields,
    }
    try:
        METRICS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with METRICS_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str))
            handle.write("\n")
        _append_csv_row(METRICS_CSV, METRICS_CSV_HEADER, payload)
    except Exception:
        return


@contextmanager
def measure_time(event: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Контекст-менеджер для метрик длительности операций."""
    started = time.perf_counter()
    mutable_fields: dict[str, Any] = dict(fields)
    try:
        yield mutable_fields
    except Exception as exc:  # noqa: BLE001
        mutable_fields.setdefault("status", "error")
        mutable_fields.setdefault("error_type", exc.__class__.__name__)
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        track_metric(event, duration_ms=duration_ms, **mutable_fields)


def archive_logs(*, older_than_days: int = 7) -> dict[str, int]:
    """Архивирует старые логи в `logs/archive/` (gzip)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(days=max(1, older_than_days))

    archived = 0
    skipped = 0

    for path in LOGS_DIR.rglob("*"):
        if not path.is_file():
            continue
        if ARCHIVE_DIR in path.parents:
            continue
        if not _is_archivable_log(path):
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            skipped += 1
            continue
        if mtime >= cutoff:
            continue
        rel = path.relative_to(LOGS_DIR)
        dst = ARCHIVE_DIR / f"{rel}.gz"
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("rb") as src, gzip.open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            path.unlink()
            archived += 1
        except Exception:
            skipped += 1

    return {"archived": archived, "skipped": skipped}


def _is_archivable_log(path: Path) -> bool:
    name = path.name.lower()
    if name in {
        "llm_costs.csv",
        "llm_costs_summary.json",
        "metrics.jsonl",
        "metrics.csv",
        "alerts.jsonl",
        "alerts.csv",
    }:
        return False
    if name.endswith(".log"):
        return True
    if ".log." in name:
        return True
    if name.endswith(".jsonl"):
        return True
    if name.endswith(".csv"):
        return True
    return False


def _append_csv_row(path: Path, header: list[str], payload: dict[str, Any]) -> None:
    known = {key: payload.get(key) for key in header if key != "extra_json"}
    extra = {key: value for key, value in payload.items() if key not in known}
    known["extra_json"] = json.dumps(extra, ensure_ascii=False, default=str) if extra else ""

    path.parent.mkdir(parents=True, exist_ok=True)
    need_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        if need_header:
            writer.writeheader()
        writer.writerow(known)
