#!/usr/bin/env python3
"""Simulate Kilo agent request with tools + streaming."""
import json
import time
import urllib.request

url = "http://localhost:8080/v1/chat/completions"
body = {
    "model": "grok",
    "stream": True,
    "messages": [
        {"role": "system", "content": "You are Kilo Code assistant."},
        {"role": "user", "content": "работаешь?"},
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"target_file": {"type": "string"}},
                    "required": ["target_file"],
                },
            },
        }
    ],
}

t0 = time.time()
req = urllib.request.Request(
    url,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    content_parts = []
    tool_chunks = []
    finish = None
    got_done = False
    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if line == "data: [DONE]":
            got_done = True
            break
        if not line.startswith("data: "):
            continue
        chunk = json.loads(line[6:])
        choice = chunk["choices"][0]
        delta = choice.get("delta", {})
        if "content" in delta and delta["content"]:
            content_parts.append(delta["content"])
        if "tool_calls" in delta:
            tool_chunks.append(delta["tool_calls"])
        if choice.get("finish_reason"):
            finish = choice["finish_reason"]

elapsed = time.time() - t0
print("elapsed_s:", round(elapsed, 2))
print("got_done:", got_done)
print("finish:", finish)
print("content:", "".join(content_parts))
print("tool_chunks:", len(tool_chunks))
