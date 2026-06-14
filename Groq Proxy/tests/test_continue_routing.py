#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_pipeline import (
    synthesize_backend_failure_response,
    synthesize_continue_tool,
)


def _tools():
    return [
        {
            "function": {
                "name": "list_files",
                "description": "list",
                "parameters": {"properties": {"path": {}}},
            }
        },
        {
            "function": {
                "name": "read_file",
                "description": "read",
                "parameters": {"properties": {"path": {}}},
            }
        },
        {
            "function": {
                "name": "attempt_completion",
                "description": "done",
                "parameters": {"properties": {"result": {}}},
            }
        },
    ]


def test_continue_after_list_files_routes_read():
    messages = [
        {"role": "user", "content": "проанализируй репо, найди ANALYSIS_AND_IMPROVEMENTS.md"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {"name": "list_files", "arguments": '{"path":"."}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": "- ANALYSIS_AND_IMPROVEMENTS.md\n- README.md\n- backend.py",
        },
    ]
    routed = synthesize_continue_tool(messages, _tools())
    assert routed is not None
    _content, tool_calls = routed
    assert tool_calls[0]["function"]["name"] == "read_file"
    args = tool_calls[0]["function"]["arguments"]
    assert "ANALYSIS_AND_IMPROVEMENTS.md" in args


def test_backend_failure_returns_completion_tool():
    synthesized = synthesize_backend_failure_response(
        _tools(),
        "Grok исчерпал лимит шагов. Нажми Retry.",
    )
    assert synthesized is not None
    _content, tool_calls = synthesized
    assert tool_calls[0]["function"]["name"] == "attempt_completion"
    assert "лимит" in tool_calls[0]["function"]["arguments"]


if __name__ == "__main__":
    test_continue_after_list_files_routes_read()
    test_backend_failure_returns_completion_tool()
    print("OK")
