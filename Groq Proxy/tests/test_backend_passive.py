#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import BackendResult, is_backend_failure, passive_cli_mode, _effective_permission_mode
from bridge_guards import classify_backend_result
from phase_router import grok_permission_mode_for_phase
from response_pipeline import grok_wrapper_indicates_failure, unwrap_grok_cli_stdout_auto


def test_passive_cli_default_on():
    old = os.environ.pop("GROK_PASSIVE_CLI", None)
    try:
        assert passive_cli_mode() is True
        assert _effective_permission_mode(None) == "plan"
        assert grok_permission_mode_for_phase("agent") == "plan"
    finally:
        if old is not None:
            os.environ["GROK_PASSIVE_CLI"] = old


def test_wrapper_cancelled_is_failure():
    raw = json.dumps(
        {
            "text": "",
            "stopReason": "Cancelled",
            "sessionId": "sess-1",
        }
    )
    text, meta = unwrap_grok_cli_stdout_auto(raw, "json")
    assert grok_wrapper_indicates_failure(meta, text) == "wrapper_cancelled_empty"
    result = BackendResult(stdout=raw, stderr="Error: max turns reached\n", returncode=1, backend="grok-cli:json", elapsed_s=50)
    assert is_backend_failure(result)
    ev = classify_backend_result(result, parse_text=text, grok_meta=meta)
    assert not ev.ok
    assert not ev.retry_planner


def test_max_turns_no_planner_retry():
    result = BackendResult(stdout="", stderr="Error: max turns reached\n", returncode=1, backend="grok-cli:json", elapsed_s=50)
    ev = classify_backend_result(result)
    assert ev.code == "max_turns"
    assert not ev.retry_planner


if __name__ == "__main__":
    test_passive_cli_default_on()
    test_wrapper_cancelled_is_failure()
    test_max_turns_no_planner_retry()
    print("OK")
