# Deferred Branch Notes

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
