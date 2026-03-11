"""Общий слой наблюдаемости: логирование, алерты и метрики."""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
METRICS_LOG = LOG_DIR / "metrics.jsonl"
ALERTS_LOG = LOG_DIR / "alerts.jsonl"
ERRORS_LOG = LOG_DIR / "errors.log"

_CONFIG_LOCK = threading.Lock()
_CONFIGURED_SERVICES: set[str] = set()
_ALERT_LAST_SENT: dict[str, float] = {}
_ALERT_LOCK = threading.Lock()
_BASE_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())


class GzipRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler с gzip-сжатием архивов."""

    def __init__(self, filename: Path, max_bytes: int, backup_count: int) -> None:
        super().__init__(
            filename=filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        self.namer = self._namer
        self.rotator = self._rotator

    @staticmethod
    def _namer(default_name: str) -> str:
        return f"{default_name}.gz"

    @staticmethod
    def _rotator(source: str, dest: str) -> None:
        with open(source, "rb") as src, gzip.open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.remove(source)


class JsonFormatter(logging.Formatter):
    """Лог в JSONL-формате для удобной агрегации."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "service": self._service,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _BASE_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Читаемый формат для консоли."""

    def __init__(self, service: str) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        parts = [message, f"service={self._service}"]
        request_id = getattr(record, "request_id", None)
        if request_id:
            parts.append(f"request_id={request_id}")
        event_code = getattr(record, "event_code", None)
        if event_code:
            parts.append(f"event_code={event_code}")
        return " | ".join(parts)


class AlertHandler(logging.Handler):
    """Отдельный алерт-канал: alerts.jsonl + optional Telegram."""

    def __init__(self, service: str) -> None:
        super().__init__(level=logging.ERROR)
        self._service = service
        self._cooldown_sec = max(0, settings.alerts_cooldown_sec)

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.ERROR:
            return
        if not settings.alerts_enabled:
            return

        message = record.getMessage()
        request_id = getattr(record, "request_id", None)
        event_code = getattr(record, "event_code", None)
        fingerprint = f"{self._service}:{record.name}:{event_code or '-'}:{message}"

        now = time.time()
        with _ALERT_LOCK:
            last_sent = _ALERT_LAST_SENT.get(fingerprint)
            if last_sent is not None and (now - last_sent) < self._cooldown_sec:
                return
            _ALERT_LAST_SENT[fingerprint] = now

        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "service": self._service,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "request_id": request_id,
            "event_code": event_code,
        }
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with ALERTS_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False))
                handle.write("\n")
        except Exception:
            return

        chat_id = settings.alerts_telegram_chat_id
        if not chat_id or not settings.telegram_bot_token:
            return

        text = (
            f"ALERT [{self._service}] {record.levelname}\n"
            f"{message}\n"
            f"request_id={request_id or '-'}"
        )
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        try:
            httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        except Exception:
            return


def ensure_log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _build_level() -> int:
    level = (settings.log_level or "INFO").strip().upper()
    return getattr(logging, level, logging.INFO)


def configure_logging(service: str) -> None:
    """Централизованная настройка логов для backend/worker/bot."""

    with _CONFIG_LOCK:
        if service in _CONFIGURED_SERVICES:
            return

        ensure_log_dir()
        root = logging.getLogger()
        root.handlers.clear()

        level = _build_level()
        root.setLevel(level)

        max_bytes = max(1, settings.log_max_mb) * 1024 * 1024
        backup_count = max(1, settings.log_backup_count)

        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(TextFormatter(service))

        service_file = GzipRotatingFileHandler(
            filename=LOG_DIR / f"{service}.log",
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
        service_file.setLevel(level)
        service_file.setFormatter(JsonFormatter(service))

        error_file = GzipRotatingFileHandler(
            filename=ERRORS_LOG,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
        error_file.setLevel(logging.ERROR)
        error_file.setFormatter(JsonFormatter(service))

        root.addHandler(console)
        root.addHandler(service_file)
        root.addHandler(error_file)
        root.addHandler(AlertHandler(service))

        _CONFIGURED_SERVICES.add(service)


def append_metric(event: str, **fields: Any) -> None:
    """Append-only метрики для мониторинга ошибок и длительности."""

    if not settings.metrics_enabled:
        return
    try:
        ensure_log_dir()
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        with METRICS_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str))
            handle.write("\n")
    except Exception:
        return


def summarize_metrics(minutes: int = 60) -> dict[str, Any]:
    """Агрегирует метрики за окно времени."""

    since = datetime.now(timezone.utc).timestamp() - (max(1, minutes) * 60)
    counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    durations: list[float] = []
    error_events = 0
    total = 0

    if not METRICS_LOG.exists():
        return {
            "window_minutes": minutes,
            "total_events": 0,
            "events": {},
            "status": {},
            "error_events": 0,
            "avg_duration_ms": None,
            "p95_duration_ms": None,
        }

    with METRICS_LOG.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_raw = row.get("ts")
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            if ts < since:
                continue

            total += 1
            event = str(row.get("event", "unknown"))
            counts[event] = counts.get(event, 0) + 1

            status = row.get("status")
            if status is not None:
                key = str(status)
                status_counts[key] = status_counts.get(key, 0) + 1
                if key == "error":
                    error_events += 1

            if row.get("level") in {"ERROR", "CRITICAL"}:
                error_events += 1

            duration = row.get("duration_ms")
            if isinstance(duration, (int, float)):
                durations.append(float(duration))

    durations.sort()
    avg_duration = round(sum(durations) / len(durations), 2) if durations else None
    if durations:
        idx = max(0, min(len(durations) - 1, int(0.95 * (len(durations) - 1))))
        p95 = round(durations[idx], 2)
    else:
        p95 = None

    return {
        "window_minutes": minutes,
        "total_events": total,
        "events": counts,
        "status": status_counts,
        "error_events": error_events,
        "avg_duration_ms": avg_duration,
        "p95_duration_ms": p95,
    }
