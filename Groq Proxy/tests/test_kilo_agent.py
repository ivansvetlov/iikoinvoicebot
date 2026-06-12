#!/usr/bin/env python3
"""Simulate Kilo agent flow: tools required + tool error recovery."""
import json
import urllib.request

URL = "http://localhost:8080/v1/chat/completions"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "attempt_completion",
            "description": "Complete the task",
            "parameters": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
                "required": ["result"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file",
            "parameters": {
                "type": "object",
                "properties": {"target_file": {"type": "string"}},
                "required": ["target_file"],
            },
        },
    },
]


def post(messages, stream=True):
    body = {"model": "grok", "stream": stream, "messages": messages, "tools": TOOLS}
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    content = []
    tool_calls = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            delta = chunk["choices"][0].get("delta", {})
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("tool_calls"):
                tool_calls.extend(delta["tool_calls"])
    return "".join(content), tool_calls


print("=== round 1: работаешь? ===")
r1_content, r1_tools = post([{"role": "user", "content": "работаешь?"}])
print("content:", repr(r1_content))
print("tool_calls:", len(r1_tools), r1_tools[:1] if r1_tools else [])

print("=== round 2: Kilo tool error ===")
messages = [
    {"role": "user", "content": "работаешь?"},
    {"role": "assistant", "content": "Да, работаю!"},
    {"role": "user", "content": "[error] you did not use a tool in your previous response"},
]
r2_content, r2_tools = post(messages)
print("content:", repr(r2_content))
print("tool_calls:", len(r2_tools), r2_tools[:1] if r2_tools else [])
print("ok:", (not r1_content or r1_tools) and r2_tools)
