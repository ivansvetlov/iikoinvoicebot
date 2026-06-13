#!/usr/bin/env python3
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompt_pipeline import (
    conversation_key,
    is_grok_resume_turn,
    build_resume_delta_prompt,
    prepare_kilo_prompt,
)
from session_store import GrokSessionStore, resume_sessions_enabled


def test_conversation_key_stable_across_turns():
    first = [{"role": "user", "content": "проанализируй проект"}]
    follow = first + [
        {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "file body"},
    ]
    assert conversation_key(first) == conversation_key(follow)
    assert conversation_key(first) != conversation_key([{"role": "user", "content": "другая задача"}])


def test_is_grok_resume_turn():
    opening = [{"role": "user", "content": "hi"}]
    assert not is_grok_resume_turn(opening)
    cont = opening + [
        {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    assert is_grok_resume_turn(cont)


def test_resume_delta_prompt_shape():
    filler = "x" * 500
    messages = [{"role": "user", "content": "проанализируй весь репозиторий подробно"}]
    for i in range(8):
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": f"c{i}", "function": {"name": "read_file", "arguments": f'{{"path":"f{i}.py"}}'}}
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": filler})
    tools = [{"function": {"name": "read_file", "description": "read", "parameters": {"properties": {"path": {}}}}}]
    full = prepare_kilo_prompt(messages, tools=tools)
    delta = build_resume_delta_prompt(messages, tools=tools)
    assert "SESSION CONTINUE" in delta
    assert len(delta) < len(full)


def test_session_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sessions.json")
        store = GrokSessionStore(persist_path=path, ttl_s=3600)
        store.set("abc123", "sess-uuid-1")
        assert store.get("abc123") == "sess-uuid-1"
        store.clear("abc123")
        assert store.get("abc123") is None
        assert os.path.isfile(path)


def test_resume_flag_default_off():
    old = os.environ.pop("GROK_RESUME_SESSIONS", None)
    try:
        assert resume_sessions_enabled() is False
    finally:
        if old is not None:
            os.environ["GROK_RESUME_SESSIONS"] = old


if __name__ == "__main__":
    test_conversation_key_stable_across_turns()
    test_is_grok_resume_turn()
    test_resume_delta_prompt_shape()
    test_session_store_roundtrip()
    test_resume_flag_default_off()
    print("OK")
