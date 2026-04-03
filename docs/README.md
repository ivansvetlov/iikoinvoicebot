# Telegram bot + backend для накладных -> iiko

## Что важно сейчас
- Точки входа приложения вынесены в `app/entrypoints/`:
  - `app.entrypoints.main` (ASGI backend)
  - `app.entrypoints.worker`
  - `app.entrypoints.bot`
- Документация находится в `docs/`.
- Файлы деплоя находятся в `deploy/`.
- Шаблон окружения: `config/.env.example`.

## Быстрый запуск
1. Скопировать `config/.env.example` в `.env` и заполнить значения.
2. Установить зависимости: `pip install -r requirements.txt`.
3. Запустить backend: `uvicorn app.entrypoints.main:app --host 127.0.0.1 --port 8000`.
4. Запустить worker: `python -m app.entrypoints.worker`.
5. Запустить bot: `python -m app.entrypoints.bot`.

## Docker
- Compose: `deploy/deploy/docker-compose.yml`
- Dockerfile: `deploy/deploy/Dockerfile`
- Nginx config: `deploy/deploy/nginx_bot.conf`

Пример:
```bash
docker compose -f deploy/deploy/docker-compose.yml up -d --build
```

## Навигация по документации
- `docs/START_HERE_NEW_CHAT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEV_SETUP.md`
- `docs/DEBUG.md`
- `docs/AGENT_HANDOFF.md`
- `docs/TODO.md`
- `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md`
- `docs/exp/BUSINESS_INTEGRATIONS_PLAN.md`
- `docs/exp/IIKO_STORE_CATALOG.md`
- `docs/exp/IIKO_RMS_DEMO_PROFILE_2026-03-16.md`
