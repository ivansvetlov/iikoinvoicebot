from __future__ import annotations

import unittest

from app.bot.max_tokens import assert_distinct_max_tokens


class MaxTokenGuardTests(unittest.TestCase):
    def test_allows_distinct_tokens(self) -> None:
        assert_distinct_max_tokens("token-a", "token-b")

    def test_allows_one_empty(self) -> None:
        assert_distinct_max_tokens("token-a", "")
        assert_distinct_max_tokens("", "token-b")

    def test_rejects_identical_tokens(self) -> None:
        with self.assertRaises(RuntimeError):
            assert_distinct_max_tokens("same", "same")


if __name__ == "__main__":
    unittest.main()
