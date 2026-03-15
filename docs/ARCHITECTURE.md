# ARCHITECTURE

## Компоненты
- `app.entrypoints.main` — ASGI backend (FastAPI).
- `app.entrypoints.worker` — RQ worker.
- `app.entrypoints.bot` — Telegram bot (polling).
- `app/api.py` — HTTP endpoints (`/health`, `/process`, `/process-batch`, `/metrics/summary`, webhook).
- `app/tasks.py` — обработка задач очереди.
- `app/services/pipeline.py` — основной пайплайн распознавания и загрузки в iiko.

## Инфраструктура
- Redis + RQ для очереди.
- SQLAlchemy для task store.
- Логи/метрики/алерты через `app/observability.py`.
- Деплой-файлы в `deploy/`:
  - `deploy/deploy/Dockerfile`
  - `deploy/deploy/docker-compose.yml`
  - `deploy/deploy/nginx_bot.conf`
- Конфиги в `config/`:
  - `config/config/.env.example`

## Поток
1. Bot отправляет файл в backend.
2. Backend валидирует вход, сохраняет payload и ставит задачу в RQ.
3. Worker обрабатывает задачу через pipeline.
4. Результат уходит пользователю и (опционально) в iiko.

## Risks
- `P0`: Batch flow regression. `process-batch` jobs are enqueued, but worker path takes only `files[0]` in `app/tasks.py`; this can silently drop other files from a batch.
- `P1`: Queue timeout risk. Jobs are enqueued without explicit `job_timeout`; long OCR/LLM/iiko runs may exceed default RQ timeout under load.
- `P1`: Single worker bottleneck. Current topology is one RQ worker process; queue latency can grow quickly during burst traffic.
- `P1`: Stateful bot memory model. Runtime state is stored in in-memory dict/set structures in bot manager; horizontal scaling and restart resilience are limited.
- `P1`: Local credentials storage. iiko credentials are persisted in `data/users.json`; this is a security and operational risk for multi-user or shared hosts.

## Risk Mitigation Priorities
1. Fix batch execution path in worker (`files[]` handling, true batch pipeline call).
2. Set explicit RQ timeouts/retry policy per job type and add dead-letter/failed-job handling.
3. Introduce worker horizontal scaling profile and queue depth monitoring.
4. Move bot runtime state and user credentials to durable storage with access controls.

