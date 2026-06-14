#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import orchestrate_turn, synthesize_extra_read, synthesis_orchestrator_enabled
from synthesis_pipeline import build_synthesis_prompt


def _tools():
    return [
        {"function": {"name": "list_files", "parameters": {"properties": {"path": {}}}}},
        {"function": {"name": "read_file", "parameters": {"properties": {"path": {}}}}},
        {"function": {"name": "attempt_completion", "parameters": {"properties": {"result": {}}}}},
    ]


def test_orchestrator_enabled():
    os.environ["GROK_ORCHESTRATOR"] = "synthesis"
    assert synthesis_orchestrator_enabled()


def test_analysis_starts_with_list():
    messages = [{"role": "user", "content": "проанализируй архитектуру репо"}]
    d = orchestrate_turn(messages, _tools())
    assert d.action == "mechanical"
    assert d.tool_calls[0]["function"]["name"] == "list_files"


def test_after_list_routes_read():
    messages = [
        {"role": "user", "content": "анализ проекта"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "c1", "function": {"name": "list_files", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ANALYSIS_AND_IMPROVEMENTS.md"},
    ]
    d = orchestrate_turn(messages, _tools())
    assert d.action == "mechanical"
    assert d.tool_calls[0]["function"]["name"] == "read_file"


def test_after_read_goes_synthesis():
    messages = [
        {"role": "user", "content": "анализ проекта"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": '{"path":"a.md"}'}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "# Analysis\ncontent here"},
    ]
    d = orchestrate_turn(messages, _tools())
    assert d.action == "synthesis"
    assert d.synthesis_kind == "post_read"


def test_greeting_synthesis():
    messages = [{"role": "user", "content": "работаешь?"}]
    d = orchestrate_turn(messages, _tools())
    assert d.action == "synthesis"
    assert d.synthesis_kind == "greeting"


def test_synthesis_prompt_has_grok_voice():
    messages = [
        {"role": "user", "content": "анализ"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "file body"},
    ]
    prompt = build_synthesis_prompt(messages, _tools(), kind="post_read")
    assert "You are Grok" in prompt
    assert "TOOL RESULT" in prompt or "file body" in prompt
    assert "list_files" not in prompt.split("SYNTHESIS MODE")[0] or "gathering is done" in prompt


def test_extra_read_second_file():
    messages = [
        {"role": "user", "content": "глубокий анализ проекта"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "l1", "function": {"name": "list_files", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "l1", "content": "ANALYSIS_AND_IMPROVEMENTS.md\nREADME.md"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "r1", "function": {"name": "read_file", "arguments": '{"path":"ANALYSIS_AND_IMPROVEMENTS.md"}'}}],
        },
        {"role": "tool", "tool_call_id": "r1", "content": "analysis content"},
    ]
    extra = synthesize_extra_read(messages, _tools())
    assert extra is not None
    assert "README" in extra[1][0]["function"]["arguments"]


if __name__ == "__main__":
    test_orchestrator_enabled()
    test_analysis_starts_with_list()
    test_after_list_routes_read()
    test_after_read_goes_synthesis()
    test_greeting_synthesis()
    test_synthesis_prompt_has_grok_voice()
    test_extra_read_second_file()
    print("OK")
