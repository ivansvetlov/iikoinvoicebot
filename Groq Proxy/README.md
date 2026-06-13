# Groq Proxy

OpenAI-compatible HTTP proxy that routes **Kilo Code** (and other OpenAI clients) to **Grok CLI**.

- **Endpoint:** `http://localhost:8080/v1`
- **Model:** `grok`
- **API key:** any value (e.g. `dummy`)

## Quick start

```bash
cd "Groq Proxy"
python start_grok.py
```

Kilo Code settings: Provider **OpenAI Compatible**, Base URL above, Model `grok`.

Stop: `python stop_grok.py` or GUI `python scripts/grok_manager.py`.

## Layout

```
Groq Proxy/
├── openai_proxy.py      # HTTP server (entry point)
├── backend.py           # Grok CLI LLM backend
├── prompt_pipeline.py   # Kilo prompt compression + intent routing
├── response_pipeline.py # JSON tool_calls parsing
├── mcp_grok_adapter.py  # legacy ACP adapter (optional)
├── start_grok.py        # start grok agent + proxy
├── stop_grok.py
├── scripts/             # diagnostics & GUI manager
├── tests/               # manual/integration checks
├── logs/                # runtime logs (gitignored)
└── PROGRESS.md          # integration status
```

## Logs

All runtime logs go to `logs/`:

- `proxy_requests.log` — per-request timings and raw backend output
- `proxy.out.log` / `proxy.err.log` — proxy process stdout/stderr

## Tests

From this directory:

```bash
python -m pytest tests/ -q
# or run individual scripts, e.g. python tests/test_dedup.py
```

## Contributing / Analysis notes
See detailed project analysis and improvement suggestions in the internal review (run via Kilo or review the agent findings). Key areas: test automation, response pipeline robustness, streaming edge cases, multi-turn state, logging/observability, and packaging.

## Parent repo

This folder lives inside the [iikoinvoicebot](https://github.com/ivansvetlov/iikoinvoicebot) monorepo as a **standalone dev tool**, unrelated to the Telegram/iiko invoice pipeline. Git branch: `feature/groq-proxy-kilo`.
