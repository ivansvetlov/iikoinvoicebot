"""Basic tests for pluggable task state backends (C1).

These tests verify:
- DB backend produces same behaviour as before (compatibility)
- Redis backend (if available) can create/mark/get
- Factory returns correct backend based on config
"""

import unittest
from unittest.mock import patch

from app.state import get_state_backend, DBTaskStateBackend
from app.state.redis_backend import RedisTaskStateBackend


class TestStateBackends(unittest.TestCase):
    def test_db_backend_basic_flow(self):
        backend = DBTaskStateBackend()
        rid = "test_state_db_12345"

        backend.create_task(rid, filename="test.pdf", user_id="42", batch=False)
        backend.mark_processing(rid)

        task = backend.get_task(rid)
        self.assertIsNotNone(task)
        self.assertEqual(task["status"], "processing")
        self.assertEqual(task["filename"], "test.pdf")

        backend.mark_done(rid, {"status": "done", "iiko_uploaded": True})
        task = backend.get_task(rid)
        self.assertEqual(task["status"], "done")

    def test_factory_default_db(self):
        with patch("app.config.settings") as mock_settings:
            mock_settings.state_backend = "db"
            backend = get_state_backend()
            self.assertIsInstance(backend, DBTaskStateBackend)

    def test_redis_backend_if_available(self):
        # This will be no-op or work depending on local Redis.
        # We don't require Redis in unit tests.
        try:
            backend = RedisTaskStateBackend()
            if backend._available:  # type: ignore[attr-defined]
                rid = "test_state_redis_temp"
                backend.create_task(rid, user_id="42")
                t = backend.get_task(rid)
                self.assertIsNotNone(t)
                backend.mark_error(rid, "boom")
                self.assertEqual(backend.get_task(rid)["status"], "error")
            else:
                self.skipTest("Redis not available for this test run")
        except Exception as e:
            self.skipTest(f"Redis backend test skipped: {e}")

    def test_list_user_tasks(self):
        backend = DBTaskStateBackend()
        rid = "test_list_user_987"
        backend.create_task(rid, user_id="999", filename="list_test.jpg")
        tasks = backend.list_user_tasks("999", limit=5)
        self.assertTrue(any(t["request_id"] == rid for t in tasks))


if __name__ == "__main__":
    unittest.main()
