#!/usr/bin/env python3
"""Simulate Kilo Code streaming request and verify SSE termination."""
import json
import urllib.request

url = "http://localhost:8080/v1/chat/completions"
body = {
    "model": "grok",
    "stream": True,
    "messages": [{"role": "user", "content": "работаешь? Ответь кратко."}],
    "tools": [],
}
req = urllib.request.Request(
    url,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
print("POST stream=true ...")
with urllib.request.urlopen(req, timeout=120) as resp:
    print("status:", resp.status)
    print("headers:", dict(resp.headers))
    chunks = []
    done = False
    for raw_line in resp:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            continue
        print("LINE:", line[:200])
        if line == "data: [DONE]":
            done = True
        elif line.startswith("data: "):
            chunks.append(line[6:])
    print("---")
    print("got_done:", done)
    print("chunk_count:", len(chunks))
    if chunks:
        last = json.loads(chunks[-1])
        print("last_finish:", last["choices"][0].get("finish_reason"))
