"""Tests for MAX-only recognition race."""
from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.bot.messages import Msg
from app.channels import is_max_channel_user
from app.channels.users import should_use_max_hybrid_only

from app.schemas import InvoiceItem
from app.services.recognition_race import race_image_recognition
from experiments.max_invoice_bot.processing_status import processing_stage_message


class MaxChannelTests(unittest.TestCase):
    def test_is_max_channel_user(self) -> None:
        self.assertTrue(is_max_channel_user("max:42"))
        self.assertFalse(is_max_channel_user("6106711925"))
        self.assertFalse(is_max_channel_user(None))

    def test_should_use_max_hybrid_only(self) -> None:
        self.assertTrue(
            should_use_max_hybrid_only(
                "max:42",
                source_type="image",
                use_fast_parser=False,
            )
        )
        self.assertFalse(
            should_use_max_hybrid_only(
                "6106711925",
                source_type="image",
                use_fast_parser=False,
            )
        )
        self.assertFalse(
            should_use_max_hybrid_only(
                "max:42",
                source_type="pdf",
                use_fast_parser=False,
            )
        )

    def test_hybrid_progress_messages_exist(self) -> None:
        self.assertIn("Читаю документ", Msg.HYBRID_PROGRESS_OCR)
        self.assertIn("Распознаю позиции", Msg.HYBRID_PROGRESS_LLM)
        self.assertNotIn("SotaOCR", Msg.HYBRID_PROGRESS_OCR)
        self.assertNotIn("gpt-4o", Msg.HYBRID_PROGRESS_LLM)


class ProcessingStageTests(unittest.TestCase):
    def test_rotates_stages(self) -> None:
        first = processing_stage_message(0.0)
        second = processing_stage_message(8.0)
        self.assertNotEqual(first, second)
        self.assertIn(first, Msg.PROCESSING_STAGES)
        self.assertIn(second, Msg.PROCESSING_STAGES)


class RecognitionRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_vision_wins_first(self) -> None:
        from app.services.pipeline import InvoicePipelineService

        service = InvoicePipelineService()
        item = InvoiceItem(name="Молоко", unit_amount=Decimal("1"), total_cost=Decimal("10"))
        vision_payload = (
            {"items": [{"description": "Молоко", "quantity": 1}]},
            [item],
            [],
        )

        with patch.object(
            service,
            "_try_sotaocr_hybrid_core",
            AsyncMock(return_value=None),
        ) as hybrid_mock:
            with patch.object(
                service,
                "_run_llm_pass",
                AsyncMock(return_value=vision_payload),
            ):
                with patch.object(service, "_detect_garbage_items", return_value=[]):
                    result = await race_image_recognition(
                        service,
                        prompt="test",
                        prepared_filename="a.jpg",
                        prepared_content=b"x",
                        original_filename="a.jpg",
                        original_content=b"x",
                        text_hint="",
                        user_id="max:1",
                        request_id="req-race-1",
                    )

        hybrid_mock.assert_called_once()
        self.assertEqual(result.winner, "vision")
        self.assertEqual(len(result.items), 1)

    async def test_hybrid_wins_first(self) -> None:
        from app.services.pipeline import InvoicePipelineService

        service = InvoicePipelineService()
        item = InvoiceItem(name="Хлеб", unit_amount=Decimal("2"), total_cost=Decimal("20"))
        hybrid_payload = (
            {"items": [{"description": "Хлеб", "quantity": 2}]},
            [item],
            ["sotaocr_hybrid_used"],
        )

        async def slow_vision(*_a, **_k):
            await asyncio.sleep(5)
            return ({}, [], [])

        with patch.object(
            service,
            "_try_sotaocr_hybrid_core",
            AsyncMock(return_value=hybrid_payload),
        ):
            with patch.object(service, "_run_llm_pass", side_effect=slow_vision):
                result = await race_image_recognition(
                    service,
                    prompt="test",
                    prepared_filename="a.jpg",
                    prepared_content=b"x",
                    original_filename="a.jpg",
                    original_content=b"x",
                    text_hint="",
                    user_id="max:1",
                    request_id="req-race-2",
                )

        self.assertEqual(result.winner, "hybrid")


if __name__ == "__main__":
    unittest.main()
