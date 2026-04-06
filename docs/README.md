# Telegram bot + backend для накладных -> iiko

## Что делает MVP
- Бот принимает фото, PDF, DOCX (и текстовые файлы).
- Backend извлекает текст (PDF/DOCX/TXT) и пытается выделить товарные позиции.
- Позиции отправляются в iiko через Playwright (UI-автоматизация).

## Правила для агентов
- Основные правила и стандарты: `docs/AGENTS.md`.
- Проверенные команды запуска/диагностики: `docs/DEBUG.md`.

## Архитектура
- Краткий обзор модулей и потоков: `docs/ARCHITECTURE.md`

## Структура

### Корень проекта

Основные файлы в корневой директории:
- `README.md` — этот файл, общее описание.
- `docs/TODO.md` — dashboard + план работ/идей.
- `docs/TESTCASES.md` — список QA-сценариев.
- `requirements.txt` — зависимости Python.
- `docker-compose.yml`, `Dockerfile`, `nginx_bot.conf` — файлы для контейнерного деплоя.
- `.env`, `.env.example` — конфиги окружения (секреты / токены **не должны** попадать в git).
- `dialogue_dump.jsonl` — дамп старого диалога с Codex (исторический артефакт, не используется рантаймом).

Служебные папки в корне:
- `app/` — код backend-а, пайплайна и интеграций (подробности в `app/README.md`).
  - `app/entrypoints/` — runtime-скрипты запуска (`bot.py`, `worker.py`, `main.py`, `invoice_llm_client.py`).
- `scripts/` — дев-скрипты (`diagnose_request.py`, `cleanup_dev_artifacts.py` и т.п.).
- `docs/` — документация для разработчика/агента (`AGENT_HANDOFF.md`, `DEV_SETUP.md`, `BOT_COMMAND_MATRIX.md`, `BOT_EVENT_CODES.md`).
- `data/` — рабочие данные (БД, job-директории); не коммитится.
- `logs/` — runtime-логи; не коммитятся.
- `tmp/` — временные диагностические файлы; можно очищать.
- `.venv/` — локальное виртуальное окружение Python.

### Кодовая структура
- `app/api.py` - FastAPI endpoint `/process`
- `app/services/pipeline.py` - orchestration обработки
- `app/parsers/file_text_extractor.py` - извлечение текста из PDF/DOCX/TXT
- `app/parsers/invoice_parser.py` - эвристический парсинг позиций
- `app/iiko/playwright_client.py` - загрузка в iiko через браузер
- `app/entrypoints/bot.py` - Telegram бот
- `app/entrypoints/invoice_llm_client.py` - LLM клиент для пакетной обработки

## LLM клиент
```bash
python app/entrypoints/invoice_llm_client.py --path ./invoices --model gpt-4o-mini
```

## Установка
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Конфиг
1. Скопируйте `.env.example` в `.env`.
2. Заполните:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `IIKO_LOGIN_URL`, `IIKO_USERNAME`, `IIKO_PASSWORD`
- при необходимости селекторы `IIKO_SELECTORS_*` под вашу iiko-страницу.

### Быстрое переключение polling/webhook
Скрипт обновляет `.env` без ручного редактирования.

Polling:
```powershell
.\scripts\set_mode.ps1 -Mode polling
```

Webhook:
```powershell
.\scripts\set_mode.ps1 -Mode webhook -WebhookUrl https://bot.iikoinvoicebot.ru -WebhookSecret <secret>
```

## Запуск
Backend:
```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

Bot:
```bash
python app/entrypoints/bot.py
```

## Очередь задач (Redis + RQ)
1. Запустите Redis.
2. Установите зависимости:
```bash
pip install -r requirements.txt
```
3. Запустите воркер:
```bash
python app/entrypoints/worker.py
```

## Хранилище задач (Postgres)
Для истории и статусов задач используется БД. По умолчанию можно оставить SQLite,
но для продакшена рекомендуется Postgres.

Переменная окружения:
```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/iiko
```

В Docker используйте хост `postgres`:
```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@postgres:5432/iiko
```

Сервис `postgres` уже есть в `docker-compose.yml`.

## Webhook
1. Установите `USE_WEBHOOK=true` и `WEBHOOK_URL=https://<ваш-домен>`
2. Сервер FastAPI будет принимать `/telegram/webhook`

## Docker Deploy
1. Заполните `.env` (ключи и webhook).
2. Соберите и запустите:
```bash
docker compose up -d --build
```
3. Проверка:
```bash
curl http://<server>:8000/health
```
