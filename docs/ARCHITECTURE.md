# ARCHITECTURE

## Components
- `app.entrypoints.main` - FastAPI backend.
- `app.entrypoints.worker` - RQ worker.
- `app.entrypoints.bot` - Telegram bot.
- `app/services/pipeline.py` - invoice processing pipeline (OCR/LLM + iiko integration).
- `app/tasks.py` - queue task execution and result publishing.

## Infrastructure
- Redis + RQ queue.
- SQLAlchemy task/user state storage.
- Observability layer: `app/observability.py`.
- Deployment artifacts in `deploy/`.

## Request flow
1. Telegram bot receives file(s).
2. Backend validates input and enqueues task (`/process`, `/process-batch`).
3. Worker processes payload through pipeline.
4. Result is returned to user and optionally sent to iiko.

## iiko integration track
- Primary target: iikoServer API import path.
- Fallback path: existing non-API flow (where enabled by feature flags).
- Mapping details: `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md`.

## Active risks
- `P1` Worker throughput under burst load.
- `P1` Bot runtime-state still partly in process memory.
- `P1` Credentials in local JSON storage need protected replacement.

## Priorities
1. Finish first end-to-end import on RMS demo stand.
2. Move bot state to durable storage.
3. Migrate credential storage to secure flow.
