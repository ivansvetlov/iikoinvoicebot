#!/usr/bin/env python3
"""Simulate Kilo's triple-request pattern for a simple greeting."""
import json
import time
import urllib.request

URL = "http://localhost:8080/v1/chat/completions"


def post(messages, tools=None, stream=True):
    body = {"model": "grok", "stream": stream, "messages": messages}
    if tools is not None:
        body["tools"] = tools
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = []
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            delta = chunk["choices"][0].get("delta", {})
            if delta.get("content"):
                content.append(delta["content"])
        return "".join(content)


messages = [{"role": "user", "content": "работаешь?"}]
tools = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"target_file": {"type": "string"}}}}}]

r1 = post(messages, tools=tools)
print("round1:", repr(r1))

messages.append({"role": "assistant", "content": r1})
time.sleep(0.5)
r2 = post(messages, tools=tools)
print("round2:", repr(r2))

messages.append({"role": "assistant", "content": r2 or "Да, работаю!"})
time.sleep(0.5)
r3 = post(messages, tools=tools)
print("round3:", repr(r3))
print("ok:", r1 and not r2 and not r3)
