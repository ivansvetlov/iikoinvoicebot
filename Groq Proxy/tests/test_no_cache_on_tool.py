from prompt_pipeline import already_answered_last_user, needs_agent_continuation, _user_turn_key


def should_suppress(messages):
    if needs_agent_continuation(messages):
        return None
    if messages[-1].get("role") != "user":
        return None
    if already_answered_last_user(messages):
        return "history_has_assistant_reply"
    return None


msgs = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "<task>\nпривет! работаешь?\n</task>"},
    {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "attempt_completion", "arguments": "{}"}}]},
    {"role": "tool", "content": "done", "tool_call_id": "1"},
    {"role": "assistant", "content": None, "tool_calls": [{"id": "2", "function": {"name": "attempt_completion", "arguments": "{}"}}]},
    {"role": "tool", "content": "done2", "tool_call_id": "2"},
]
print("needs_continuation:", needs_agent_continuation(msgs))
print("suppress:", should_suppress(msgs))
print("turn_key:", _user_turn_key(msgs)[:80])
assert needs_agent_continuation(msgs)
assert should_suppress(msgs) is None
print("OK")
