# DEBUG.md — проверенные приёмы запуска и отладки

> Этот файл — шпаргалка по **проверенным** командам запуска/остановки и
> отладки рантаймов в проекте. Сюда попадает только то, что реально
> было запущено и проверено.

## Backend (FastAPI + Uvicorn)

### Запуск

```bash
.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Проверено:
- команда запускает сервер без ошибок (при установленном venv и зависимостях);
- `/health` отвечает `{"status": "ok"}`:

```bash
curl http://127.0.0.1:8000/health
```

- `/metrics/summary` отвечает агрегатами метрик:

```bash
curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"
```

### Остановка

- В терминале с uvicorn: `Ctrl+C`.
- Процесс завершается, порт 8000 освобождается.

### Логи

- При запуске через команду выше вывод идёт в тот же терминал.
- При запуске через прод-скрипты/сервис — логи пишутся в `logs/backend.log`.

---

## Worker (RQ)

### Запуск

```bash
.venv\Scripts\python.exe worker.py
```

Проверено:
- воркер подключается к Redis по `settings.redis_url`;
- в логе есть строка `Worker ready, listening on queue ...`.

Проверка через rqinfo:

```bash
.venv\Scripts\rqinfo.exe
```

Ожидается хотя бы один воркер в очереди `default`.

### Остановка

- В терминале с worker.py: `Ctrl+C`.

---

## Telegram-бот (polling)

### Запуск (для разработки)

Самый надёжный способ — через `scripts/dev_run_all.py` (см. ниже).
Если нужно отдельно:

```bash
.venv\Scripts\python.exe bot.py
```

Проверено:
- бот поднимается, в консоли видно `Run polling for bot`;
- при `/start` в Telegram бот отвечает и логирует события в `logs/bot.log`.

**Важно:** нельзя запускать `bot.py` несколько раз параллельно — Telegram
возвращает `TelegramConflictError: terminated by other getUpdates request`.

### Остановка

- В терминале с bot.py: `Ctrl+C`.

---

## Dev-оркестратор: `scripts/dev_run_all.py` (backend + worker + bot)

Особенность (проверено): перед запуском `bot.py` скрипт пытается остановить другие
процессы `bot.py` (в том же venv/проекте), чтобы не ловить `TelegramConflictError`.

### Запуск всех компонент одной командой

```bash
.venv\Scripts\python.exe scripts\dev_run_all.py
```

Проверено:
- скрипт последовательно запускает backend и ждёт `/health`;
- затем запускает worker и бота;
- в случае ошибки на любом шаге пишет `ERROR` и пытается остановить
  уже запущенные процессы.

После успешного старта показывает PID'ы и ждёт `Ctrl+C` для остановки
всех процессов.

---

## Быстрая проверка окружения: `scripts/dev_status.py`

```bash
.venv\Scripts\python.exe scripts\dev_status.py
```

Проверено:
- при запущенном backend с `/health` и хотя бы одном воркере RQ выводит:

```text
backend: OK (http://127.0.0.1:8000/health)
worker: OK (workers: ...)
```

- при незапущенном backend: `backend: UNAVAILABLE (...)`.
- при отсутствии воркеров: `worker: NO ACTIVE WORKERS`.

---

## Где искать логи

- `logs/bot.log` — события бота, статусы отправки/ошибок.
- `logs/backend.log` — запросы к API, ошибки пайплайна.
- `logs/worker.log` — работа воркера, исключения в задачах.
- `logs/errors.log` — общий error-канал (backend/worker/bot).
- `logs/alerts.jsonl` — алерты с cooldown (и, при настройке, дубли в Telegram).
- `logs/metrics.jsonl` — мониторинг ошибок и времени обработки (append-only).
- `logs/llm_costs.csv` — стоимость LLM по заявкам (заполняется после
  успешного вызова LLM, даже если документ не признан накладной).
- `logs/llm_costs_summary.json` — накопительные итоги по стоимости (USD/RUB).

Ротация:
- `*.log` файлы ротируются по `LOG_MAX_MB` и архивируются в `*.gz`.
- число архивов задаётся `LOG_BACKUP_COUNT`.

Быстрая сводка метрик:
```bash
.venv\Scripts\python.exe scripts\metrics_report.py --minutes 60
```

---

## Отладка по коду заявки / коду события

- Короткий код заявки (`HHMMSS_mmm`) показывается пользователю в ответе
  бота. Для диагностики:

```bash
.venv\Scripts\python.exe scripts\diagnose_request.py 000736_800
```

- Для ботовых ошибок используются коды событий (`BOT_*`), которые
  печатаются в последних строках сообщений. Актуальный справочник:
  `docs/BOT_EVENT_CODES.md` (включая архивный `BOT_PENDING_TIMEOUT`).
  По коду ищем строки в `logs/bot.log`.
