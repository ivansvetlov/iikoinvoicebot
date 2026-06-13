#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from response_pipeline import unwrap_grok_cli_stdout, parse_assistant_response

GROK_JSON_SAMPLE = """
{
  "text": "{\\"content\\":null,\\"tool_calls\\":[{\\"name\\":\\"attempt_completion\\",\\"arguments\\":{\\"result\\":\\"pong\\"}}]}",
  "stopReason": "EndTurn",
  "sessionId": "019ec1c8-5882-7bb3-8591-ec2041aee2ef",
  "requestId": "bb8145c8-dda0-4ec3-a24b-9239537ac89e"
}
"""


def test_unwrap_grok_json():
    text, meta = unwrap_grok_cli_stdout(GROK_JSON_SAMPLE, "json")
    assert "tool_calls" in text
    assert meta.get("session_id") == "019ec1c8-5882-7bb3-8591-ec2041aee2ef"
    content, tools = parse_assistant_response(
        text,
        allowed_tool_names=["attempt_completion"],
    )
    assert tools
    assert tools[0]["function"]["name"] == "attempt_completion"
    args = json.loads(tools[0]["function"]["arguments"])
    assert args["result"] == "pong"


def test_plain_passthrough():
    plain = '{"content": null, "tool_calls": []}'
    text, meta = unwrap_grok_cli_stdout(plain, "plain")
    assert text == plain
    assert meta == {}


if __name__ == "__main__":
    test_unwrap_grok_json()
    test_plain_passthrough()
    print("OK")
