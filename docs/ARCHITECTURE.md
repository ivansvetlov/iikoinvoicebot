# Архитектура (краткий обзор)

## Цель
Зафиксировать понимание текущей архитектуры проекта (бот, backend, worker, очередь, БД, LLM, iiko), чтобы упростить поддержку, отладку и развитие.

## Структура и ключевые компоненты

### Верхний уровень
- `app/api.py`: FastAPI‑приложение с `/health`, `/process`, `/process-batch`, `/telegram/webhook` и инициализацией БД/вебхука.
- `app/entrypoints/bot.py`: точка входа Telegram‑бота (polling), защита от дублей через lock‑файл.
- `app/entrypoints/worker.py`: точка входа RQ‑воркера, слушающего очередь Redis.
- `app/entrypoints/main.py`: ASGI‑обёртка (`app` из `app.api`) для uvicorn/gunicorn.

### Конфигурация и инфраструктура
- `app/config.py`: `Settings` на базе Pydantic, чтение `.env`, все ключевые ENV (Telegram, Redis, DB, OpenAI, iiko, лимиты).
- `app/db.py`: SQLAlchemy `engine`, `SessionLocal`, `init_db()`.
- `app/models.py`: модели (в частности `TaskRecord` для задач).
- `app/task_store.py`: CRUD по задачам (create/processing/done/error).
- `app/queue.py`: обёртки над Redis и RQ `Queue`.
- `docker-compose.yml`, `Dockerfile`, `nginx_bot.conf`, `.env.example`: окружение и деплой.

### Бизнес‑логика и сервисы
- `app/services/pipeline.py`: `InvoicePipelineService` — основной конвейер: извлечение текста → LLM → валидация/фильтрация → запись логов → выгрузка в iiko (Playwright) или fallback в CSV/XLSX импорт-файл.
- `app/parsers/...`: извлечение текста из файлов (PDF, изображения, DOCX, текст).
- `app/services/user_store.py`: JSON‑хранилище для user‑state (логин/пароль iiko, `pdf_mode`).
- `app/services/invoice_validator.py`: эвристика «похоже ли на счёт».
- `app/iiko/playwright_client.py`: Playwright‑клиент для загрузки позиций в iiko.
- `app/iiko/import_export.py`: генерация CSV/XLSX файла для ручного импорта в iiko при недоступности Playwright.
- `app/schemas.py`: Pydantic‑схемы `InvoiceItem`, `InvoiceParseResult`, `ProcessResponse` и т.п.

### Бот и задачи
- `app/bot/manager.py`: `TelegramBotManager` (aiogram), команды `/start`, `/mode*`, `/split`, `/done`, `/cancel`, приём документов/фото, сбор батчей, отправка в backend.
- `app/tasks.py`: `process_invoice_task(payload_path)` — целевая функция для RQ, вызывает `InvoicePipelineService`, обновляет БД и шлёт сообщения пользователю.

### Скрипты разработки и утилиты
- `scripts/dev_run_all.py`: запуск backend + worker + bot одним скриптом, убийство дубликатов бота на Windows.
- `scripts/dev_status.py`: проверка, запущены ли backend и worker.
- Прочие утилиты: `scripts/check_bom.py`, `scripts/strip_bom.py`, `scripts/cleanup_dev_artifacts.py`, `scripts/dump_task_results.py`, `scripts/diagnose_request.py`.

## Основные потоки выполнения

### HTTP backend‑поток
- Старт через uvicorn / `scripts/dev_run_all.py` / ASGI (`main:app`).
- На старте: конфигурирует вебхук (опционально) и инициализирует БД.
- `/process` и `/process-batch`:
  - Проверяют файлы и лимиты, сохраняют входные данные в `data/jobs/<request_id>/`.
  - Создают запись задачи в БД и ставят `process_invoice_task` в очередь RQ.
  - Возвращают `ProcessResponse(status="queued")`.

### Поток Telegram‑бота (polling/webhook)
- Polling: запуск `app/entrypoints/bot.py` → `TelegramBotManager.run()`.
- Webhook: Telegram бьёт в `/telegram/webhook`, backend делегирует апдейты тому же `TelegramBotManager`.
- Бот:
  - Ведёт авторизацию iiko и настройки пользователя (`pdf_mode`, split).
  - При получении файла(ов) отправляет их на backend `/process` или `/process-batch` с `push_to_iiko`, `user_id`, `pdf_mode`, `chat_id`.

### Поток воркера / конвейера
- `app/entrypoints/worker.py` запускает RQ‑воркер, слушающий очередь Redis.
- На задачу `process_invoice_task`:
  - Загружает payload из `data/jobs`, помечает задачу как `processing` в БД.
  - Читает файл(ы), вызывает `InvoicePipelineService.process(...)` (или `process_batch`).
  - Обновляет запись задачи (`done` / `error`) и отправляет/редактирует сообщение в Telegram.

## Интеграции
- OpenAI: `/v1/files` и `/v1/responses` (tool calling `parse_invoice`), трекинг токенов и стоимости.
- iiko: Playwright‑клиент для прямой загрузки + fallback через CSV/XLSX импорт-файл.
- Redis + RQ: асинхронная очередь задач.
- SQLAlchemy БД: хранение статуса задач.

## Возможные следующие шаги
- Углублённый разбор: детальнее разобрать, например, только LLM‑конвейер (`pipeline.py`) или только логику бота и сценарии UX.
- Диагностика/оптимизация: найти узкие места (скорость обработки, устойчивость к ошибкам iiko/LLM, повторный запуск задач).
- Рефакторинг/улучшения: предложить структурные улучшения (слои, интерфейсы, тестируемость) без изменения текущего поведения.
- Инструменты разработки: донастройка скриптов, logging, метрик, health‑checkов под вашу инфраструктуру.
