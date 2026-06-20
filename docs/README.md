# Telegram bot + backend для накладных -> iiko

## Что делает MVP
- Бот принимает фото, PDF, DOCX (и текстовые файлы).
- Backend извлекает текст (PDF/DOCX/TXT) и пытается выделить товарные позиции.
- Позиции отправляются в iiko через server-side API (HTTP).
- Если прямая API-выгрузка недоступна, backend готовит файл импорта CSV/XLSX для ручной загрузки в iiko.

## Оглавление docs/

| Папка | Назначение |
|-------|------------|
| docs/governance/ | handoff, audit, deferred notes |
| docs/operations/ | DEBUG, DEV_SETUP, TESTCASES, bot matrices |
| docs/architecture/ | ARCHITECTURE, OPTIMIZATION |
| docs/iiko/ | demo stand, API gaps, E2E runbooks |
| docs/planning/ | TODO, feature plans |
| docs/assets/ | dashboard SVG и прочие артефакты |
| experiments/ | experimental tracks (не stage6 runtime) |

## Правила для агентов
- Основные правила и стандарты: `docs/AGENTS.md`.
- Проверенные команды запуска/диагностики: `docs/operations/DEBUG.md`.

## Архитектура
- Краткий обзор модулей и потоков: `docs/architecture/ARCHITECTURE.md`
- Текущие пробелы по iiko API: `docs/iiko/IIKO_API_GAPS.md`

## Планы и аудит
| Документ | Назначение | Статус |
|----------|------------|--------|
| `docs/planning/TODO.md` | Dashboard + приоритеты | canonical |
| `docs/governance/AUDIT_REMEDIATION_PLAN.md` | Post-audit трек | canonical |
| `docs/governance/COMPREHENSIVE_AUDIT.md` | Полный аудит 2026-04-26 | historical snapshot |
| `docs/iiko/INVOICE_FLOW_TESTING.md` | Тестирование unit flow + UX | active runbook |
| `docs/planning/MENU_DOMAIN_EXPANSION_PLAN.md` | Категории, типы продуктов, техкарты | planned |
| `docs/planning/BRANCH_WAIT_OPTIMIZATION_PLAN.md` | Оптимизация LLM wait time | separate branch |
| `docs/governance/DEFERRED_BRANCH_NOTES.md` | Отложенные решения | reference |
| `docs/governance/PROJECT_CLONE_PROMPT.md` | Blueprint для нового проекта | reference |

## Prompts
- `prompts/invoice_unit_resolution_fork.txt` — LLM fallback для неоднозначных единиц (`INVOICE_FLOW_LLM_PROMPT_FORK_PATH`).
- `prompts/invoice_parser_units_fork.txt` — экспериментальный fork парсера единиц.
- Правило: менять только через PR; не коммитить секреты и client-specific данные.

## Структура

### Корень проекта

Основные файлы в корневой директории:
- `docs/README.md` — этот файл, общее описание.
- `docs/planning/TODO.md` — dashboard + план работ/идей.
- `docs/operations/TESTCASES.md` — список QA-сценариев.
- `requirements.txt` — зависимости Python.
- `docker-compose.yml`, `Dockerfile`, `nginx_bot.conf` — файлы для контейнерного деплоя.
- `.env`, `.env.example` — конфиги окружения (секреты / токены **не должны** попадать в git).
- `dialogue_dump.jsonl` — дамп старого диалога с Codex (исторический артефакт, не используется рантаймом).

Служебные папки в корне:
- `app/` — код backend-а, пайплайна и интеграций (подробности в `app/README.md`).
  - `app/entrypoints/` — runtime-скрипты запуска (`bot.py`, `worker.py`, `main.py`, `invoice_llm_client.py`).
- `scripts/` — дев-скрипты (`diagnose_request.py`, `dev_run_all.py`, `run_grok_bridge.ps1` и т.п.).
- `experiments/` — экспериментальные треки; см. `experiments/grok_telegram_bridge/` (Grok ↔ Telegram bridge).
- `docs/` — документация (подпапки: `governance/`, `operations/`, `architecture/`, `iiko/`, `planning/`).
- `data/` — рабочие данные (БД, job-директории); не коммитится.
- `logs/` — runtime-логи; не коммитятся.
- `tmp/` — временные диагностические файлы; можно очищать.
- `.venv/` — локальное виртуальное окружение Python.

### Кодовая структура
- `app/api.py` - FastAPI endpoint `/process`
- `app/services/pipeline.py` - orchestration обработки
- `app/parsers/file_text_extractor.py` - извлечение текста из PDF/DOCX/TXT
- `app/parsers/invoice_parser.py` - эвристический парсинг позиций
- `app/iiko/server_client.py` - загрузка в iiko через server-side API
- `app/iiko/import_export.py` - экспорт позиций в CSV/XLSX для ручного импорта в iiko
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
```

## Конфиг
1. Скопируйте `.env.example` в `.env`.
2. Заполните:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `IIKO_TRANSPORT`, `IIKO_API_BASE_URL`, `IIKO_API_AUTH_PATH`, `IIKO_API_UPLOAD_PATH`
- `IIKO_USERNAME`, `IIKO_PASSWORD`
- `IIKO_IMPORT_FALLBACK_ENABLED` (true/false)
- `IIKO_IMPORT_FORMAT` (`csv` или `xlsx`)
- `IIKO_IMPORT_EXPORT_DIR` (папка для файлов импорта)

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
