# Start Here (New Chat)

If you open a new chat and need to continue work fast, follow this order.

## 1) Read first (5 minutes)
1. `docs/AGENT_HANDOFF.md` - current state, recent changes, branch context.
2. `docs/TODO.md` - what is done vs pending.
3. `docs/DEBUG.md` - verified run and diagnostics commands.
4. `docs/TERMUX_VIBE_WRAPPER_PLAYBOOK.md` - phone/SSH/vibe wrapper setup and migration guide.
5. `docs/TERMUX_WINDOWS_VIBE_RUNBOOK.md` - strict setup/troubleshooting route for Termux -> Windows -> Vibe.

## 2) Current focus (Stage 8)
- `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md` - target mapping to iikoServer incoming invoice API.
- `docs/exp/BUSINESS_INTEGRATIONS_PLAN.md` - product/business roadmap inside iiko ecosystem.
- `docs/exp/IIKO_STORE_CATALOG.md` - market snapshot (`store.iiko.ru` and connectors).

## 3) Runtime entrypoints
- Backend: `app.entrypoints.main`
- Worker: `app.entrypoints.worker`
- Bot: `app.entrypoints.bot`

## 4) Verified local commands
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.entrypoints.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m app.entrypoints.worker
.\.venv\Scripts\python.exe -m app.entrypoints.bot
.\.venv\Scripts\python.exe scripts\dev_status.py
```

## 5) Next implementation steps
1. Implement `iikoServer` auth/session client in app service layer.
2. Implement mapper `InvoiceItem -> incomingInvoiceItemDto` with unit/pack conversion.
3. Add idempotency guard (`external document key`) and duplicate prevention.
4. Add dual-path feature flag (`iikoServer` primary, Playwright fallback).

## 6) Git hygiene before changes
```powershell
git status -sb
git branch -vv
```
