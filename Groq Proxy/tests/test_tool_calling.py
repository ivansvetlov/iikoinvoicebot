#!/usr/bin/env python3
"""Quick self-test for the tool-calling path in the grok openai proxy shim.
Run with: python test_tool_calling.py
"""
import json
import time
import re
import sys
sys.path.insert(0, ".")

# Import the functions from the proxy (they are not in a module, so exec the relevant defs)
# For simplicity we duplicate the small pure helpers here + import by exec for fidelity.

import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "openai_proxy.py"), "r", encoding="utf-8") as f:
    proxy_src = f.read()

# Extract just the three helper functions by crude cut (keeps us in sync)
# In real we'd factor them out, but for the test this works.
namespace = {}
exec(compile(proxy_src.split("if __name__ == '__main__':")[0], "openai_proxy.py", "exec"), namespace)

build_full_prompt = namespace["build_full_prompt"]
extract_tool_calls = namespace["extract_tool_calls"]
format_messages_for_prompt = namespace["format_messages_for_prompt"]
extract_system_prompt = namespace.get("extract_system_prompt")
build_prompt_for_backend = namespace.get("build_prompt_for_backend")


def test_prompt_building():
    messages = [
        {"role": "system", "content": "You are a helpful coding assistant."},
        {"role": "user", "content": "Read the file README.md and tell me the first heading."},
    ]
    tools = [
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read a file from disk",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
        }},
        {"type": "function", "function": {
            "name": "run_terminal_cmd",
            "description": "Execute a command",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}
        }}
    ]
    p = build_full_prompt(messages, tools=tools)
    assert "AVAILABLE TOOLS" in p
    assert "read_file" in p
    assert "tool call read_file with" in p.lower() or "tool call" in p.lower()
    assert "USER:" in p and "SYSTEM:" in p
    print("✓ prompt building includes history + tools + instructions")


def test_extract_simple():
    text = """I need to look at the file first.
tool call read_file with
path is README.md
"""
    calls = extract_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "read_file"
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["path"] == "README.md"
    print("✓ extract simple single tool call")


def test_extract_json_arg():
    text = """Planning the edit.
tool call apply_diff with
path is src/foo.py
diff is {"old":"print(1)","new":"print(2)"}
"""
    calls = extract_tool_calls(text)
    assert len(calls) == 1
    args = json.loads(calls[0]["function"]["arguments"])
    assert isinstance(args.get("diff"), dict)
    print("✓ extract with JSON structured arg value")


def test_no_tools_no_extraction():
    text = "Hello there, the answer is 42."
    calls = extract_tool_calls(text)
    assert calls == []
    print("✓ no false positive extraction on plain text")


def test_multi_turn_history_and_tool_result():
    messages = [
        {"role": "user", "content": "List dir"},
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "list_dir", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "[\"file1.py\", \"README.md\"]"},
        {"role": "user", "content": "Now read README.md"},
    ]
    p = build_full_prompt(messages, tools=None)
    assert "TOOL RESULT" in p
    assert "list_dir" in p
    assert "Now read README.md" in p
    print("✓ history roundtrip with prior tool result preserved")


def test_system_extraction_and_backend_split():
    """Verify grok SYSTEM support: system messages are extracted for --append-system-prompt
    and are no longer forced into the main conv prompt string for the backend call.
    """
    if not extract_system_prompt or not build_prompt_for_backend:
        print("⚠ skipping system split test (helpers not found in source)")
        return

    messages = [
        {"role": "system", "content": "You are Grok, a precise coding agent. Always be concise."},
        {"role": "user", "content": "Create a hello world in Python."},
    ]
    tools = [{"type": "function", "function": {"name": "write_file", "description": "write", "parameters": {"type": "object"}}}]

    sys_part = extract_system_prompt(messages)
    assert sys_part and "precise coding agent" in sys_part

    conv, system_append = build_prompt_for_backend(messages, tools=tools)
    # conv should contain the user turn but not the SYSTEM: line
    assert "USER:" in conv
    assert "Create a hello world" in conv
    assert "SYSTEM:" not in conv

    # system_append should contain the original system + the full tool instruction block
    assert "precise coding agent" in system_append
    assert "AVAILABLE TOOLS" in system_append
    assert "write_file" in system_append
    print("✓ system extraction + backend split (system goes to ACP flag, conv is clean)")


if __name__ == "__main__":
    test_prompt_building()
    test_extract_simple()
    test_extract_json_arg()
    test_no_tools_no_extraction()
    test_multi_turn_history_and_tool_result()
    test_system_extraction_and_backend_split()
    print("\nAll local logic tests passed.")
