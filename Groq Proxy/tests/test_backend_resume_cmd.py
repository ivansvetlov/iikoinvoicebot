#!/usr/bin/env python3
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend


def test_grok_cli_resume_and_permission_flags():
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        return mock.Mock(stdout='{"text":"{}"}', stderr="", returncode=0)

    with mock.patch.object(backend.subprocess, "run", side_effect=fake_run):
        backend.invoke_grok_cli_llm(
            "hello",
            output_format="json",
            resume_session_id="sess-abc",
            permission_mode="plan",
        )

    cmd = captured[0]
    assert "--resume" in cmd
    idx = cmd.index("--resume")
    assert cmd[idx + 1] == "sess-abc"
    assert "--permission-mode" in cmd
    pidx = cmd.index("--permission-mode")
    assert cmd[pidx + 1] == "plan"


if __name__ == "__main__":
    test_grok_cli_resume_and_permission_flags()
    print("OK")
