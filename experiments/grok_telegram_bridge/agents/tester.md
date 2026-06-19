# Tester agent (bridge documentation)

The bridge does **not** spawn a custom subprocess for testing.

It uses Grok CLI built-in verification, identical to the terminal:

```bash
grok -p "your task" --check --always-approve --resume <sessionId>
```

This triggers the **check-work** skill loop: a `general-purpose` verifier subagent
reviews diffs, runs tests, and returns `VERDICT: PASS|FAIL`.

## Telegram triggers

| Trigger | Effect |
|---------|--------|
| `/check <prompt>` | Always adds `--check` |
| `/verify` | Alias via regex in `tester.py` |
| `GROK_BRIDGE_AUTO_CHECK=true` | `--check` on code-like prompts |
| Words: «проверь», «verify» | `--check` |

## Why not MCP / cron?

- **MCP**: Grok CLI already has MCP from `~/.grok/config.toml` — bridge inherits it automatically.
- **Cron**: not needed for chat; bridge is long-polling. Scheduled jobs = separate future track.
