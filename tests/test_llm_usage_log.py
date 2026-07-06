"""Tests for per-call OpenAI usage logging."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.llm_usage_log import (
    append_cost_row,
    estimate_cost,
    log_openai_response,
    set_usage_context,
    reset_usage_context,
)


class LlmUsageLogTests(unittest.TestCase):
    def test_estimate_cost_unknown_model_still_returns_tokens(self) -> None:
        cost = estimate_cost({"input_tokens": 100, "output_tokens": 20}, "unknown-model-x")
        self.assertIsNotNone(cost)
        assert cost is not None
        self.assertEqual(cost["input_tokens"], 100)
        self.assertEqual(cost["output_tokens"], 20)

    def test_log_openai_response_appends_one_row_per_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "llm_costs.csv"
            summary_path = Path(temp_dir) / "llm_costs_summary.json"
            with patch("app.services.llm_usage_log.LLM_COSTS_LOG", log_path):
                with patch("app.services.llm_usage_log.LLM_COSTS_SUMMARY", summary_path):
                    log_openai_response(
                        {"usage": {"input_tokens": 10, "output_tokens": 5}},
                        model="gpt-4o-mini",
                        call_kind="parse",
                        user_id="max:1",
                        request_id="20260706_120000_000_max_1",
                    )
                    log_openai_response(
                        {"usage": {"input_tokens": 12, "output_tokens": 6}},
                        model="gpt-4o-mini",
                        call_kind="parse_trunc_retry",
                        user_id="max:1",
                        request_id="20260706_120000_000_max_1",
                    )

            rows = list(csv.DictReader(log_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["call_kind"], "parse")
            self.assertEqual(rows[1]["call_kind"], "parse_trunc_retry")

    def test_context_fallback_for_nested_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "llm_costs.csv"
            summary_path = Path(temp_dir) / "llm_costs_summary.json"
            tokens = set_usage_context(user_id="42", request_id="20260706_130000_000_42")
            try:
                with patch("app.services.llm_usage_log.LLM_COSTS_LOG", log_path):
                    with patch("app.services.llm_usage_log.LLM_COSTS_SUMMARY", summary_path):
                        append_cost_row(
                            user_id=None,
                            request_id=None,
                            call_kind="unit_resolver",
                            cost=estimate_cost(
                                {"input_tokens": 3, "output_tokens": 1},
                                "gpt-4o-mini",
                            )
                            or {},
                        )
            finally:
                reset_usage_context(tokens)

            row = next(csv.DictReader(log_path.read_text(encoding="utf-8").splitlines()))
            self.assertEqual(row["user_id"], "42")
            self.assertEqual(row["request_id"], "20260706_130000_000_42")


if __name__ == "__main__":
    unittest.main()