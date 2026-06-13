#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phase_router import (
    resolve_grok_phase,
    grok_permission_mode_for_phase,
    two_phase_enabled,
)


def _tools():
    return [
        {"function": {"name": "read_file", "description": "read", "parameters": {}}},
        {"function": {"name": "write_to_file", "description": "write", "parameters": {}}},
        {"function": {"name": "attempt_completion", "description": "done", "parameters": {}}},
    ]


def test_planner_for_analysis():
    messages = [{"role": "user", "content": "проанализируй архитектуру"}]
    assert resolve_grok_phase(messages, _tools()) == "planner"


def test_agent_for_implement():
    messages = [{"role": "user", "content": "создай файл test.py с hello"}]
    assert resolve_grok_phase(messages, _tools()) == "agent"


def test_continue_after_read_stays_planner():
    messages = [
        {"role": "user", "content": "проанализируй проект"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": '{"path":"a.py"}'}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "code"},
    ]
    assert resolve_grok_phase(messages, _tools()) == "planner"


def test_permission_mode_plan_when_enabled():
    old = os.environ.get("GROK_TWO_PHASE")
    os.environ["GROK_TWO_PHASE"] = "1"
    try:
        assert two_phase_enabled() is True
        assert grok_permission_mode_for_phase("planner") == "plan"
        assert grok_permission_mode_for_phase("agent") is None
    finally:
        if old is None:
            os.environ.pop("GROK_TWO_PHASE", None)
        else:
            os.environ["GROK_TWO_PHASE"] = old


if __name__ == "__main__":
    test_planner_for_analysis()
    test_agent_for_implement()
    test_continue_after_read_stays_planner()
    test_permission_mode_plan_when_enabled()
    print("OK")
