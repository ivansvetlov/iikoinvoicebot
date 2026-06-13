#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_pipeline import (
    build_smart_history,
    build_prompt_suffixes,
    detect_intent_flags,
    trim_tool_result_text,
    count_tool_results,
    detect_intent,
    prepare_kilo_prompt,
)


def test_trim_tool_result():
    big = "x" * 10000
    out = trim_tool_result_text(big, max_chars=1000)
    assert len(out) < len(big)
    assert "truncated" in out


def test_smart_history_keeps_anchor():
    msgs = [{"role": "user", "content": "ORIGINAL TASK"}]
    for i in range(20):
        msgs.append({"role": "assistant", "content": f"a{i}"})
        msgs.append({"role": "tool", "content": "t" * 8000})
    hist = build_smart_history(msgs)
    assert hist[0]["content"] == "ORIGINAL TASK"
    assert len(hist) <= 12


def test_mixed_intent_flags():
    flags = detect_intent_flags("привет! проанализируй проект")
    assert flags["greeting"] and flags["analysis"]


def test_continue_suffix():
    msgs = [{"role": "user", "content": "go"}]
    for _ in range(3):
        msgs.append({"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "read_file", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "content": "ok"})
    assert count_tool_results(msgs) == 3
    suffix = build_prompt_suffixes(msgs, "continue")
    assert "CONTINUE MODE" in suffix


def test_long_session_suffix():
    msgs = [{"role": "user", "content": "big task"}]
    for i in range(7):
        msgs.append({"role": "tool", "content": f"r{i}"})
    suffix = build_prompt_suffixes(msgs, "continue")
    assert "LONG SESSION" in suffix


def test_prepare_under_budget():
    tools = [{"type": "function", "function": {"name": "read_file", "description": "r", "parameters": {}}}]
    p = prepare_kilo_prompt([{"role": "user", "content": "анализ"}], tools=tools)
    assert "AVAILABLE TOOLS" in p
    assert detect_intent([{"role": "user", "content": "анализ"}], tools) == "analysis"


if __name__ == "__main__":
    test_trim_tool_result()
    test_smart_history_keeps_anchor()
    test_mixed_intent_flags()
    test_continue_suffix()
    test_long_session_suffix()
    test_prepare_under_budget()
    print("OK")
