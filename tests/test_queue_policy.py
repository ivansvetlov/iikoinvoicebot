from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rq import Retry

from app import queue as queue_module


class QueuePolicyTests(unittest.TestCase):
    def test_build_policy_profiles(self) -> None:
        single = queue_module.build_invoice_job_policy(batch=False, push_to_iiko=False)
        batch = queue_module.build_invoice_job_policy(batch=True, push_to_iiko=False)
        iiko = queue_module.build_invoice_job_policy(batch=False, push_to_iiko=True)

        self.assertEqual(single.profile, "single")
        self.assertEqual(batch.profile, "batch")
        self.assertEqual(iiko.profile, "iiko")
        self.assertGreaterEqual(iiko.job_timeout, batch.job_timeout)

    def test_enqueue_uses_policy_retry_timeout_and_ttl(self) -> None:
        fake_queue = MagicMock()
        fake_job = MagicMock()
        fake_queue.enqueue.return_value = fake_job

        with (
            patch.object(queue_module, "get_queue", return_value=fake_queue),
            patch.object(queue_module.settings, "queue_timeout_batch_sec", 111),
            patch.object(queue_module.settings, "queue_retry_batch_max", 2),
            patch.object(queue_module.settings, "queue_retry_intervals_sec", "7,9"),
            patch.object(queue_module.settings, "queue_result_ttl_sec", 222),
            patch.object(queue_module.settings, "queue_failure_ttl_sec", 333),
        ):
            result = queue_module.enqueue_invoice_task(
                task_func=lambda path: path,
                payload_path="payload.json",
                batch=True,
                push_to_iiko=False,
            )

        self.assertIs(result, fake_job)
        _, kwargs = fake_queue.enqueue.call_args
        self.assertEqual(kwargs["job_timeout"], 111)
        self.assertEqual(kwargs["result_ttl"], 222)
        self.assertEqual(kwargs["failure_ttl"], 333)
        self.assertEqual(kwargs["meta"]["policy_profile"], "batch")
        self.assertIs(kwargs["on_failure"], queue_module.on_invoice_job_failed)
        self.assertIsInstance(kwargs["retry"], Retry)
        self.assertEqual(kwargs["retry"].max, 2)
        self.assertEqual(kwargs["retry"].intervals, [7, 9])


class QueueFailureHandlerTests(unittest.TestCase):
    def test_failure_handler_marks_task_error_and_emits_metric(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            payload_path.write_text(
                json.dumps({"request_id": "req-77", "chat_id": 123}),
                encoding="utf-8",
            )
            fake_job = MagicMock()
            fake_job.id = "job-1"
            fake_job.args = [str(payload_path)]

            with (
                patch.object(queue_module, "mark_error") as mark_error,
                patch.object(queue_module, "append_metric") as append_metric,
                patch.object(queue_module, "_notify_user_job_failed") as notify_user,
            ):
                queue_module.on_invoice_job_failed(
                    fake_job,
                    connection=MagicMock(),
                    exc_type=RuntimeError,
                    exc_value=RuntimeError("boom"),
                    traceback="tb",
                )

            mark_error.assert_called_once()
            mark_args = mark_error.call_args.args
            self.assertEqual(mark_args[0], "req-77")
            self.assertTrue(str(mark_args[1]).strip())
            self.assertIn("RuntimeError", mark_args[2])
            notify_user.assert_called_once_with(123, "req-77")
            append_metric.assert_called_once()


if __name__ == "__main__":
    unittest.main()
