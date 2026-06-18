# Prompt: Build a High-Standard Clone Skeleton From This Project

Use this prompt when you need to bootstrap a new project with the same product class (document intake -> recognition -> validation -> async processing -> integration export), but without dragging technical debt.

---

## 1) Copy-Paste Prompt (for an AI coding agent)

```text
You are a senior software architect and implementation engineer.
Generate a production-grade skeleton for a project in the same domain as this system:

Domain:
- Multi-channel document intake (Telegram-first)
- OCR/LLM parsing of invoices
- Validation and normalization
- Async processing via queue workers
- External accounting integration (provider API + fallback export)

Tech stack constraints:
- Python 3.12+
- FastAPI for backend
- aiogram for bot
- Redis + RQ for async jobs
- SQLAlchemy + Postgres for task/status persistence
- Pydantic Settings for config

Primary objective:
Create a clean, maintainable, observable skeleton that keeps proven strengths and removes known failure patterns.

You must produce:
1. Directory tree
2. Minimal runnable implementation for backend + bot + worker
3. Configuration contract (.env.example + typed settings)
4. Job/task model and status transitions
5. Integration client interface (provider-agnostic)
6. Observability baseline (structured logs + metrics hooks + error taxonomy)
7. Governance baseline (SECURITY, CONTRIBUTING, CODEOWNERS, PR template)
8. Test skeleton (unit + integration + e2e stubs)
9. CI baseline (tests + lint + formatting checks)
10. Migration notes from monolith-style handlers to modular architecture

Non-negotiable architecture rules:
- Keep bot, backend, and worker as separate runtime entrypoints.
- Any long-running operation must be async job-based (never block bot callback flow).
- All external providers must be wrapped in explicit clients with retry/timeouts.
- Every user-visible workflow must be idempotent by request/action key.
- Every critical state transition must be persisted and traceable.

Required runtime modules:
- app/api.py
- app/entrypoints/bot.py
- app/entrypoints/worker.py
- app/services/pipeline.py
- app/services/status_service.py
- app/integrations/accounting_client.py
- app/task_store.py
- app/config.py
- app/logging_setup.py
- app/error_codes.py

Required quality modules:
- tests/unit/
- tests/integration/
- tests/e2e/
- .github/workflows/tests.yml
- .github/workflows/lint.yml

Required documentation:
- docs/ARCHITECTURE.md
- docs/DEV_SETUP.md
- docs/DEBUG.md
- docs/TODO.md
- docs/AUDIT_REMEDIATION_PLAN.md
- docs/PROJECT_OPERATING_MODEL.md

What to keep from the current project (proven useful):
- Clear separation: bot/backend/worker
- Queue-based processing with request IDs
- Status card / progress communication pattern
- Feature flags in settings
- Integration fallback strategy (API -> export file)
- Operational scripts for local orchestration and diagnostics
- Explicit docs for architecture/debug/runbooks

What to avoid repeating (known harmful patterns):
- Monolithic bot manager that keeps growing without boundaries
- Blocking sync operations inside callback handlers
- "catch-all exception -> send duplicate message" fallback behavior
- Missing debounce/idempotency for high-frequency callbacks
- Unbounded retries / token growth without hard budgets
- Secrets or private keys in repo root
- No CI gate for merge
- Untracked local artifacts polluting the workspace

Data and state standards:
- Use a typed task state model: queued, processing, done, failed_retryable, failed_final
- Persist correlation fields: request_id, user_id, source_channel, created_at, updated_at
- Keep user secrets outside git and avoid plaintext at rest where possible
- Track reason codes for all validation/sync failures

Observability standards:
- Structured JSON logging for backend/worker/bot
- Unified short error code mapping for user-facing failures
- Metrics hooks for latency, retries, queue depth, parse quality
- Audit trail for destructive actions

Testing standards:
- Unit tests for parser/validator/integration client/error mapping
- Integration tests for API queueing and task lifecycle
- E2E smoke flow: intake -> queued -> processed -> result message
- Regression tests for idempotency and duplicate callback handling

Security standards:
- Include SECURITY.md and a private vulnerability reporting path
- Add secret scanning guidance
- Add branch protection recommendations in docs
- Enforce "no secrets in commits" checks in CI (baseline)

Deliverables format:
- First output: concise architecture rationale (1 page max)
- Second output: full file tree
- Third output: key file contents
- Fourth output: run/test commands
- Fifth output: phased migration plan (quick wins -> stabilization -> hardening)

Important:
- Prefer maintainable defaults over maximal feature count.
- Build for production readiness, not demo-only.
- Do not leave TODO-only stubs for core runtime paths.
```

---

## 2) Skeleton To Transfer As-Is (High Value)

- Runtime split:
- backend API
- bot runtime
- worker runtime
- Task queue pattern:
- enqueue from API
- process in worker
- persist task states in DB
- Integration abstraction:
- provider client behind interface
- fallback export path when provider API unavailable
- Operational support:
- local orchestration script
- health endpoint
- debug/diagnostic scripts
- Documentation spine:
- architecture
- setup
- debugging
- roadmap

---

## 3) Anti-Patterns To Explicitly Ban In The Clone

- Single mega-file handler for all bot flows.
- Inline heavy sync in UX callback path.
- Broad exception fallback that creates duplicate user messages.
- No callback debounce on state-changing actions.
- Retry loops without hard budgets and stop conditions.
- Silent integration errors without reason codes.
- Local dumps/artifacts not excluded by `.gitignore`.
- Governance files missing at repository bootstrap.

---

## 4) Acceptance Criteria For The New Clone

- New developer runs system locally in <= 20 minutes using docs only.
- Core e2e flow is testable and deterministic.
- Duplicate click/callback does not produce duplicate effects.
- Queue task lifecycle is observable end-to-end.
- Integration failures are categorized and user-safe.
- CI blocks merge on failing tests/lint.
- Security/governance baseline exists from day 1.

---

## 5) Recommended Build Sequence

1. Initialize repository governance files and CI.
2. Implement config + logging + error code taxonomy.
3. Implement backend queueing + task store lifecycle.
4. Implement worker pipeline shell with mock parser/integration.
5. Implement bot UX with idempotent callbacks.
6. Add integration client and fallback export strategy.
7. Add observability metrics and runbooks.
8. Harden with retry budgets, debounce, and regression tests.

---

## 6) Notes For This Repository

When using this prompt here:
- Keep `docs/AUDIT_REMEDIATION_PLAN.md` as governance track source-of-truth.
- Keep `docs/TODO.md` concise and product-focused.
- Log all major runtime behavior changes in handoff/history doc separately.
