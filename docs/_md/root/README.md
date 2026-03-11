# Telegram bot + backend для накладных -> iiko

## Что делает MVP
- Бот принимает фото, PDF, DOCX (и текстовые файлы).
- Backend извлекает текст (PDF/DOCX/TXT) и пытается выделить товарные позиции.
- Позиции отправляются в iiko через Playwright (UI-автоматизация).

## UX и команды (кратко)
- В списке команд Telegram отображается только `/start` (остальные команды рабочие, но скрыты).
- Один файл: бот показывает inline‑кнопки `Обработать` / `Добавить ещё`.
- 2+ файла: бот предлагает `Объединить` / `Добавить ещё`.
- PDF: показывается выбор режима `fast/accurate/продолжить`.
- Подробности и тест‑матрица: `docs/BOT_COMMAND_MATRIX.md`.
- Коды событий бота (`BOT_*`): `docs/BOT_EVENT_CODES.md`.
- Каталог текстов сообщений: `docs/BOT_MESSAGE_CATALOG.md`.

## Правила для агентов
- Основные правила и стандарты: `AGENTS.md` (в корне проекта).
- Проверенные команды запуска/диагностики: `DEBUG.md`.

## Архитектура
- Краткий обзор модулей и потоков: `docs/_md/root/ARCHITECTURE.md`

## Наблюдаемость
- API метрики: `GET /metrics/summary?window_minutes=60`
- Логи/алерты/метрики: `logs/backend.log`, `logs/worker.log`, `logs/bot.log`, `logs/errors.log`, `logs/alerts.jsonl`, `logs/metrics.jsonl`

## Структура

### Корень проекта

Основные файлы в корневой директории:
- `bot.py` — запуск Telegram-бота (polling).
- `worker.py` — запуск воркера очереди (RQ).
- `main.py` — вспомогательный вход (если нужен для утилит/отладки).
- `invoice_llm_client.py` — отдельный LLM-клиент для пакетной обработки файлов из папки.
- `README.md` — этот файл, общее описание.
- `TODO.md` — план работ/идей.
- `TESTCASES.md` — список QA-сценариев.
- `requirements.txt` — зависимости Python.
- `docker-compose.yml`, `Dockerfile`, `nginx_bot.conf` — файлы для контейнерного деплоя.
- `.env`, `.env.example` — конфиги окружения (секреты / токены **не должны** попадать в git).
- `dialogue_dump.jsonl` — дамп старого диалога с Codex (исторический артефакт, не используется рантаймом).

Служебные папки в корне:
- `app/` — код backend-а, пайплайна и интеграций (подробности в `app/README.md`).
- `scripts/` — дев-скрипты (`diagnose_request.py`, `cleanup_dev_artifacts.py` и т.п.).
- `docs/` — документация для разработчика/агента (`AGENT_HANDOFF.md`, `DEV_SETUP.md`, `BOT_COMMAND_MATRIX.md`, `BOT_EVENT_CODES.md`, `BOT_MESSAGE_CATALOG.md`).
- `data/` — рабочие данные (БД, job-директории); не коммитится.
- `logs/` — runtime-логи; не коммитятся.
- `tmp/` — временные диагностические файлы; можно очищать.
- `.veai/` — конфигурация воркфлоу Veai (шпаргалки для агента).
- `.venv/` — локальное виртуальное окружение Python.

### Кодовая структура
- `app/api.py` - FastAPI endpoint `/process`
- `app/services/pipeline.py` - orchestration обработки
- `app/parsers/file_text_extractor.py` - извлечение текста из PDF/DOCX/TXT
- `app/parsers/invoice_parser.py` - эвристический парсинг позиций
- `app/iiko/playwright_client.py` - загрузка в iiko через браузер
- `bot.py` - Telegram бот
- `invoice_llm_client.py` - LLM клиент для пакетной обработки

## LLM клиент
```bash
python invoice_llm_client.py --path ./invoices --model gpt-4o-mini
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
- `OPENAI_MODEL_IMAGE` (default `gpt-4o` for images)
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
python bot.py
```

## Очередь задач (Redis + RQ)
1. Запустите Redis.
2. Установите зависимости:
```bash
pip install -r requirements.txt
```
3. Запустите воркер:
```bash
python worker.py
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
