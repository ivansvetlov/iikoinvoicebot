# DEV_SETUP: повторяемый сценарий локального запуска

Цель: новый разработчик должен поднять backend + worker + bot одной командой, проверить статус и понять, где смотреть проблемы.

## 1. Минимальные prerequisites

1. Заполнить `.env` (как минимум `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `REDIS_URL`).
2. Установить зависимости:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
3. Запустить Redis (локально или в Docker).

## 2. Один запуск для всех процессов

```powershell
.\.venv\Scripts\python.exe scripts\dev_run_all.py
```

Что делает скрипт:
- поднимает backend и ждёт `GET /health`;
- запускает worker;
- перед запуском бота останавливает дубли `bot.py` (чтобы не ловить `TelegramConflictError`);
- запускает bot;
- по `Ctrl+C` корректно останавливает всё.

## 3. Быстрый smoke-check после старта

1. Проверить backend:
```powershell
curl http://127.0.0.1:8000/health
```
Ожидаемо:
```json
{"status":"ok"}
```

2. Проверить backend + worker:
```powershell
.\.venv\Scripts\python.exe scripts\dev_status.py
```

3. Проверить метрики наблюдаемости:
```powershell
curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"
.\.venv\Scripts\python.exe scripts\metrics_report.py --minutes 60
```

## 4. Где смотреть логи и алерты

- `logs/backend.log` — backend JSONL-лог.
- `logs/worker.log` — воркер JSONL-лог.
- `logs/bot.log` — бот JSONL-лог.
- `logs/errors.log` — общий error-канал.
- `logs/alerts.jsonl` — алерты (ошибки с cooldown, опционально дублируются в Telegram).
- `logs/metrics.jsonl` — события мониторинга времени/статусов обработки.

Ротация и архивирование:
- файлы автоматически ротируются по размеру (`LOG_MAX_MB`);
- архивы сжимаются в `*.gz`;
- количество архивов регулируется `LOG_BACKUP_COUNT`.

## 5. Важные ENV для наблюдаемости

- `LOG_LEVEL=INFO|WARNING|ERROR`
- `LOG_MAX_MB=10`
- `LOG_BACKUP_COUNT=14`
- `ALERTS_ENABLED=true|false`
- `ALERTS_COOLDOWN_SEC=300`
- `ALERTS_TELEGRAM_CHAT_ID=<chat_id>` (опционально)
- `METRICS_ENABLED=true|false`

## 6. Если снова словили TelegramConflictError

1. Остановить `dev_run_all.py` (`Ctrl+C`) или все run-конфиги в IDE.
2. Запустить `scripts/dev_run_all.py` заново.
3. Не держать параллельные ручные запуски `python bot.py` для того же токена.

## 7. Полезные ссылки

- Архитектура: `docs/_md/root/ARCHITECTURE.md`
- Команды и UX бота: `docs/BOT_COMMAND_MATRIX.md`
- Коды событий бота: `docs/BOT_EVENT_CODES.md`
- Каталог пользовательских сообщений: `docs/BOT_MESSAGE_CATALOG.md`
- Диагностика по заявке: `scripts/diagnose_request.py`
