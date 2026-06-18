# Deferred Branch Notes

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
