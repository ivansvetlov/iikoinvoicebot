# Telegram bot + backend для накладных -> iiko

## Что делает MVP
- Бот принимает фото, PDF, DOCX (и текстовые файлы).
- Backend извлекает текст (PDF/DOCX/TXT) и пытается выделить товарные позиции.
- Позиции отправляются в iiko через Playwright (UI-автоматизация).

## Структура
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
