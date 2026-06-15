from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import user_store


class UserStoreCategoryProfileTests(unittest.TestCase):
    def test_set_and_get_category_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"
            with patch.object(user_store, "USERS_FILE", users_file):
                profile = user_store.set_category_profile(
                    "42",
                    business_model=["horeca"],
                    custom_categories=["Напитки", " Молочка ", "Напитки"],
                    resolved_categories=["Напитки", "Молочка", "Бакалея"],
                )
                loaded = user_store.get_category_profile("42")

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(profile["business_model"], ["horeca"])
        self.assertEqual(profile["custom_categories"], ["Напитки", "Молочка"])
        self.assertEqual(loaded["resolved_categories"], ["Напитки", "Молочка", "Бакалея"])

    def test_global_category_bank_deduplicates_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"
            with patch.object(user_store, "USERS_FILE", users_file):
                user_store.remember_global_categories(["Напитки", "напитки", "  Молочка  "], source="test")
                user_store.remember_global_categories(["Бакалея", "Молочка"], source="test")
                names = user_store.get_global_category_bank()

        self.assertEqual(names, ["Напитки", "Молочка", "Бакалея"])

    def test_set_category_profile_updates_global_bank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            users_file = Path(temp_dir) / "users.json"
            with patch.object(user_store, "USERS_FILE", users_file):
                user_store.set_category_profile(
                    "77",
                    business_model=["retail"],
                    custom_categories=[],
                    resolved_categories=["Напитки", "Хозтовары"],
                )
                names = user_store.get_global_category_bank()

        self.assertIn("Напитки", names)
        self.assertIn("Хозтовары", names)


if __name__ == "__main__":
    unittest.main()
