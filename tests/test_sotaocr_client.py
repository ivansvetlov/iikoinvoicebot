from __future__ import annotations

import unittest
from unittest.mock import patch

from app.ocr.sotaocr_client import SotaOcrClient, SotaOcrError, SotaOcrJob


def _job_payload(**overrides: object) -> dict:
    base = {
        "id": "job_123456789",
        "account_id": "acct_123456789",
        "status": "pending",
        "page_count": 1,
        "pages_completed": 0,
        "model_profile": "fast",
        "upstream_job_id": "up_job_987654321",
        "created_at": "2026-03-24T12:00:00Z",
        "updated_at": "2026-03-24T12:00:00Z",
    }
    base.update(overrides)
    return base


class SotaOcrClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = SotaOcrClient(
            api_key="test-key-not-real",
            base_url="https://sotaocr.example",
            timeout_sec=30,
            poll_interval_sec=1.0,
            prefer_curl=False,
        )

    async def test_create_job_success(self) -> None:
        with patch.object(
            self.client,
            "_sync_request_json",
            return_value=(202, _job_payload()),
        ):
            job = await self.client.create_job(b"%PDF", "invoice.pdf")

        self.assertIsInstance(job, SotaOcrJob)
        self.assertEqual(job.id, "job_123456789")
        self.assertEqual(job.status, "pending")

    async def test_api_error_unauthorized(self) -> None:
        with patch.object(
            self.client,
            "_sync_request_json",
            side_effect=SotaOcrError(
                "Balance failed: Invalid API key",
                status_code=401,
                code="unauthorized",
            ),
        ):
            with self.assertRaises(SotaOcrError) as ctx:
                await self.client.get_balance()

        err = ctx.exception
        self.assertEqual(err.status_code, 401)
        self.assertEqual(err.code, "unauthorized")
        self.assertIn("Invalid API key", str(err))

    async def test_invalid_job_json(self) -> None:
        with patch.object(
            self.client,
            "_sync_request_json",
            side_effect=SotaOcrError(
                "Job status: invalid JSON response",
                status_code=200,
                payload="not-json",
            ),
        ):
            with self.assertRaises(SotaOcrError) as ctx:
                await self.client.get_job("job_x")

        self.assertIn("invalid JSON", str(ctx.exception))

    async def test_invalid_job_schema(self) -> None:
        with patch.object(
            self.client,
            "_sync_request_json",
            side_effect=SotaOcrError(
                "Job status: invalid job payload",
                payload={"status": "pending"},
            ),
        ):
            with self.assertRaises(SotaOcrError) as ctx:
                await self.client.get_job("job_x")

        self.assertIn("invalid job payload", str(ctx.exception))

    async def test_get_result_success(self) -> None:
        with patch.object(
            self.client,
            "_sync_request_json",
            return_value=(200, {"content": "line one\nline two", "format": "text"}),
        ):
            result = await self.client.get_result("job_1", result_format="text")

        self.assertEqual(result.content, "line one\nline two")

    async def test_requests_get_falls_back_to_curl(self) -> None:
        import requests

        client = SotaOcrClient(
            api_key="test-key-not-real",
            base_url="https://sotaocr.example",
            timeout_sec=30,
            prefer_curl=False,
        )
        with patch.object(
            client._session,
            "request",
            side_effect=requests.exceptions.ConnectionError("reset"),
        ), patch.object(
            client,
            "_curl_request_json",
            return_value=(
                200,
                {
                    "remaining_pages": 10,
                    "total_affordable_pages": 10,
                },
            ),
        ) as curl_mock:
            balance = await client.get_balance()

        curl_mock.assert_called_once()
        self.assertEqual(balance.remaining_pages, 10)

    async def test_requests_upload_falls_back_to_curl(self) -> None:
        import requests

        client = SotaOcrClient(
            api_key="test-key-not-real",
            base_url="https://sotaocr.example",
            timeout_sec=30,
            prefer_curl=False,
        )
        with patch.object(
            client._session,
            "request",
            side_effect=requests.exceptions.ConnectionError("reset"),
        ), patch.object(
            client,
            "_curl_request_json",
            return_value=(202, _job_payload()),
        ) as curl_mock:
            job = await client.create_job(b"%PDF", "invoice.pdf")

        curl_mock.assert_called_once()
        self.assertEqual(job.id, "job_123456789")


if __name__ == "__main__":
    unittest.main()
