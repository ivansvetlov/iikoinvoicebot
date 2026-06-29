# Deferred Branch Notes

## 2026-06-22 — Distributed agents / AGENT_PRIME (PAUSED)

**Status:** paused; main line — invoice bot / stage6. Не блокирует локальную разработку.

**Goal (AGENT_PRIME):** единое состояние, webhook lock, NAT/failover между локальным и серверным агентом.

**Artifacts (готовы, остаются в репо):**
- `docs/governance/AGENT_PRIME.md` — канонический промпт (TASK_1–7),
- `docs/governance/DISTRIBUTED_AGENTS_ANALYSIS.md` — результат сканирования (TASK_1),
- `app/state/` + `STATE_BACKEND` в `.env` — C1 (pluggable db/redis), тесты `tests/test_state_backends.py`,
- Grok bridges (`experiments/grok_*_bridge/`) — handoff road↔home, работают локально.

**Blocker:**
- Нет прод-сервера → C2 (webhook lock, multi-instance) и C5 (публичный failover) не к чему привязать.

**Resume when:**
1. Появился VPS/прод с nginx + webhook,
2. Нужен автоматический failover локал↔сервер (не только Tailscale для личного дашборда).

**Next steps on resume:**
1. C2: Redis lock + идемпотентный setWebhook (`app/api.py`),
2. C5: туннель/nginx + `docs/architecture/DISTRIBUTED_AGENTS.md`,
3. `IMPLEMENTATION_PLAN.md` по TASK_2 из AGENT_PRIME.

**Не откатывать:** код `app/state/` — полезен локально, default `STATE_BACKEND=db`.

## 2026-06-17 — Telegram favorites research (PAUSED)

**Status:** paused; main line is stage6 iiko E2E.

**Goal:** architect report from Saved Messages (4 sections):
1. raw extract,
2. link map,
3. utility matrix,
4. roadmap.

**Artifacts (ready, not in sprint commits):**
- `scripts/export_telegram_saved.py` (Telethon),
- env keys in `.env.example`: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`,
- output dir: `data/private/telegram_favorites/` (gitignored).

**Blockers:**
- my.telegram.org app creation unavailable («попробуйте позже»).

**Resume options:**
1. Telethon export when API credentials work,
2. Telegram Desktop JSON export → `data/private/telegram_favorites/desktop_export/`.

**Branch when resumed:** `exp/topic-pipeline-toolkit-research` (separate from `feature/stage6-*`).

## 2026-04-22 — LLM output-token retry economics

User feedback captured:
- On large documents, repeated `max_output_tokens` growth retries increase latency and cost too much.
- Current protection strategy is considered inefficient for client UX and billing.

Decision:
- Keep current branch unchanged.
- Rework this in a separate branch.

Planned optimization direction:
- Replace blind token-growth retries with a bounded strategy (single controlled retry + early failover).
- Add pre-retry guardrails by document complexity / expected row count.
- Add explicit metrics for retry reason, retry count, and cost delta vs baseline.
