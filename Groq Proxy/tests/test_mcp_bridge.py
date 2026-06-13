#!/usr/bin/env python3
import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import BackendResult
import mcp_bridge


def test_initialize_capabilities():
    resp = mcp_bridge.dispatch_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp is not None
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_has_grok_complete():
    resp = mcp_bridge.dispatch_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "grok_complete" in names
    assert "grok_proxy_health" in names


def test_tools_call_grok_complete_mocked():
    sample = BackendResult(
        stdout=json.dumps(
            {
                "text": '{"content":"hi","tool_calls":[]}',
                "sessionId": "sess-test-1",
                "stopReason": "EndTurn",
            }
        ),
        stderr="",
        returncode=0,
        backend="grok-cli:json",
        elapsed_s=1.0,
    )
    with mock.patch.object(mcp_bridge, "_invoke_grok_locked", return_value=sample):
        resp = mcp_bridge.dispatch_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "grok_complete",
                    "arguments": {"prompt": "say hi"},
                },
            }
        )
    assert resp is not None
    text = resp["result"]["content"][0]["text"]
    assert '"content": "hi"' in text or "hi" in text
    assert "session_id=sess-test-1" in text


def test_prompts_get_legacy():
    sample = BackendResult(
        stdout=json.dumps({"text": '{"content":"pong","tool_calls":[]}', "sessionId": "s1"}),
        stderr="",
        returncode=0,
        backend="grok-cli:json",
        elapsed_s=0.5,
    )
    with mock.patch.object(mcp_bridge, "_invoke_grok_locked", return_value=sample):
        resp = mcp_bridge.dispatch_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "prompts/get",
                "params": {"name": "grok_chat", "prompt": "ping"},
            }
        )
    msg = resp["result"]["messages"][0]
    assert msg["role"] == "assistant"
    assert "pong" in msg["content"]["text"]


def test_unknown_method_error():
    resp = mcp_bridge.dispatch_request({"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert resp["error"]["code"] == -32601


if __name__ == "__main__":
    test_initialize_capabilities()
    test_tools_list_has_grok_complete()
    test_tools_call_grok_complete_mocked()
    test_prompts_get_legacy()
    test_unknown_method_error()
    print("OK")
