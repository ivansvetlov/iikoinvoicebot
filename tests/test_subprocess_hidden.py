"""Tests for hidden subprocess helpers."""
from __future__ import annotations

import os
import unittest

from app.utils.subprocess_hidden import hidden_subprocess_kwargs, run_hidden


class SubprocessHiddenTests(unittest.TestCase):
    def test_hidden_kwargs_empty_off_windows(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows-only negative case")
        self.assertEqual(hidden_subprocess_kwargs(), {})

    def test_hidden_kwargs_on_windows(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows-only")
        kwargs = hidden_subprocess_kwargs()
        self.assertIn("startupinfo", kwargs)
        self.assertIn("creationflags", kwargs)

    def test_run_hidden_sc_query(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows-only")
        proc = run_hidden(["sc", "query", "eventlog"], timeout=10, text=False)
        self.assertEqual(proc.returncode, 0)
        text = (proc.stdout or b"").decode("cp866", errors="replace").upper()
        self.assertIn("RUNNING", text)


if __name__ == "__main__":
    unittest.main()