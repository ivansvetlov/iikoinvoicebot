from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import tasks


class _DummyPipeline:
    calls: dict[str, object] = {}

    async def process_batch(
        self,
        files: list[tuple[str, bytes]],
        push_to_iiko: bool = True,
        user_id: str | None = None,
        pdf_mode: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        _DummyPipeline.calls = {
            "files": files,
            "push_to_iiko": push_to_iiko,
            "user_id": user_id,
            "pdf_mode": pdf_mode,
            "request_id": request_id,
        }
        return {
            "status": "ok",
            "request_id": request_id,
            "parsed": {"items": [], "warnings": []},
            "iiko_uploaded": False,
        }

    async def process(self, *args, **kwargs):  # pragma: no cover - should never be used in this test
        raise AssertionError("Single-file process path must not be used for batch payload.")


class WorkerBatchFlowTests(unittest.TestCase):
    def test_worker_uses_process_batch_instead_of_files_zero(self) -> None:
        _DummyPipeline.calls = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            file_a = tmp / "a.txt"
            file_b = tmp / "b.txt"
            file_a.write_bytes(b"alpha")
            file_b.write_bytes(b"beta")

            payload_path = tmp / "payload.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "request_id": "req-batch-1",
                        "files": [["a.txt", str(file_a)], ["b.txt", str(file_b)]],
                        "push_to_iiko": False,
                        "user_id": "42",
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(tasks, "InvoicePipelineService", _DummyPipeline),
                patch.object(tasks, "mark_processing") as mark_processing,
                patch.object(tasks, "mark_done") as mark_done,
                patch.object(tasks, "mark_error") as mark_error,
                patch.object(tasks, "append_metric"),
            ):
                result = tasks.process_invoice_task(str(payload_path))

            self.assertEqual(result.get("status"), "ok")
            self.assertEqual(_DummyPipeline.calls.get("request_id"), "req-batch-1")
            self.assertEqual(_DummyPipeline.calls.get("push_to_iiko"), False)

            files_arg = _DummyPipeline.calls.get("files")
            self.assertIsInstance(files_arg, list)
            assert isinstance(files_arg, list)
            self.assertEqual([name for name, _ in files_arg], ["a.txt", "b.txt"])
            self.assertEqual([content for _, content in files_arg], [b"alpha", b"beta"])

            mark_processing.assert_called_once_with("req-batch-1")
            mark_done.assert_called_once()
            mark_error.assert_not_called()


if __name__ == "__main__":
    unittest.main()

