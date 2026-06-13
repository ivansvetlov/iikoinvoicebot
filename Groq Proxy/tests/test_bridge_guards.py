#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass

from bridge_guards import (
    classify_backend_result,
    classify_parse_failure,
    stderr_indicates_builtin_leak,
    validate_outbound_tool_calls,
)


@dataclass
class FakeResult:
    stdout: str
    stderr: str
    returncode: int
    elapsed_s: float = 1.0


def test_builtin_leak_fails_even_with_stdout():
    r = FakeResult(
        stdout='{"tool_calls":[{"name":"attempt_completion","arguments":{"result":"x"}}]}',
        stderr='ERROR tool_error tool_name="search_replace" model_id="grok-build"',
        returncode=1,
    )
    ev = classify_backend_result(r)
    assert not ev.ok
    assert ev.layer == "L2"
    assert ev.retry_planner


def test_ok_json():
    r = FakeResult(stdout='{"content":null,"tool_calls":[]}', stderr="", returncode=0)
    ev = classify_backend_result(r)
    assert ev.ok


def test_validate_hallucinated_tool():
    tools = [{"function": {"name": "read_file"}}]
    tcs = [{"type": "function", "function": {"name": "fake_tool", "arguments": "{}"}}]
    valid, err = validate_outbound_tool_calls(tcs, tools)
    assert err == "hallucinated_tool"
    assert not valid


def test_parse_failure():
    ev = classify_parse_failure(True)
    assert ev.layer == "L3"
    assert ev.retry_json


if __name__ == "__main__":
    assert stderr_indicates_builtin_leak("grok-build tool_error")
    test_builtin_leak_fails_even_with_stdout()
    test_ok_json()
    test_validate_hallucinated_tool()
    test_parse_failure()
    print("OK")
