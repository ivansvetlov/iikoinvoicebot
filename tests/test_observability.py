from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.bot.event_codes import BOT_BACKEND_UNAVAILABLE, event_short_code, with_event_code
from app.observability import AlertFileHandler, archive_logs, measure_time, track_metric


class BotEventCodesTests(unittest.TestCase):
    def test_with_event_code_appends_code_line(self) -> None:
        text = with_event_code("Ошибка сети", BOT_BACKEND_UNAVAILABLE)
        self.assertIn("Код: 4501", text)

    def test_event_short_code_mapping(self) -> None:
        self.assertEqual(event_short_code(BOT_BACKEND_UNAVAILABLE), "4501")


class ObservabilityMetricsTests(unittest.TestCase):
    def test_track_metric_writes_jsonl_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            metrics_path = Path(temp_dir) / "metrics.jsonl"
            metrics_csv_path = Path(temp_dir) / "metrics.csv"
            with patch("app.observability.METRICS_LOG", metrics_path), patch(
                "app.observability.METRICS_CSV", metrics_csv_path
            ):
                track_metric("http_request", status_code=200, duration_ms=12.3)

            lines = metrics_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["event"], "http_request")
            self.assertEqual(payload["status_code"], 200)
            csv_lines = metrics_csv_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(csv_lines), 2)
            self.assertIn("http_request", csv_lines[1])

    def test_measure_time_writes_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            metrics_path = Path(temp_dir) / "metrics.jsonl"
            metrics_csv_path = Path(temp_dir) / "metrics.csv"
            with patch("app.observability.METRICS_LOG", metrics_path), patch(
                "app.observability.METRICS_CSV", metrics_csv_path
            ):
                with measure_time("worker_job", status="ok", request_id="req1"):
                    time.sleep(0.001)

            payload = json.loads(metrics_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["event"], "worker_job")
            self.assertEqual(payload["status"], "ok")
            self.assertIn("duration_ms", payload)


class ObservabilityAlertsTests(unittest.TestCase):
    def test_alert_handler_writes_jsonl_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            alerts_jsonl = Path(temp_dir) / "alerts.jsonl"
            alerts_csv = Path(temp_dir) / "alerts.csv"
            with patch("app.observability.ALERTS_LOG", alerts_jsonl), patch("app.observability.ALERTS_CSV", alerts_csv):
                handler = AlertFileHandler(component="bot")
                logger = logging.getLogger("test.alerts")
                logger.setLevel(logging.ERROR)
                logger.handlers = []
                logger.addHandler(handler)
                logger.error("backend unavailable", extra={"event_code": "BOT_BACKEND_UNAVAILABLE", "event_short": "4501"})

            jsonl_lines = alerts_jsonl.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(jsonl_lines), 1)
            payload = json.loads(jsonl_lines[0])
            self.assertEqual(payload["event_short"], "4501")
            csv_lines = alerts_csv.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(csv_lines), 2)
            self.assertIn("BOT_BACKEND_UNAVAILABLE", csv_lines[1])


class ObservabilityArchiveTests(unittest.TestCase):
    def test_archive_logs_compresses_old_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir) / "logs"
            archive_dir = logs_dir / "archive"
            logs_dir.mkdir(parents=True, exist_ok=True)

            old_log = logs_dir / "backend.log.1"
            fresh_log = logs_dir / "backend.log"
            old_log.write_text("old-data", encoding="utf-8")
            fresh_log.write_text("fresh-data", encoding="utf-8")

            ten_days_ago = time.time() - 10 * 24 * 3600
            os.utime(old_log, (ten_days_ago, ten_days_ago))

            with patch("app.observability.LOGS_DIR", logs_dir), patch("app.observability.ARCHIVE_DIR", archive_dir):
                result = archive_logs(older_than_days=7)

            self.assertEqual(result["archived"], 1)
            self.assertFalse(old_log.exists())
            self.assertTrue((archive_dir / "backend.log.1.gz").exists())
            self.assertTrue(fresh_log.exists())


if __name__ == "__main__":
    unittest.main()
