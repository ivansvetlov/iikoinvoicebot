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
.venv\Scripts\python.exe -m app.entrypoints.worker
```

Проверено:
- воркер подключается к Redis по `settings.redis_url`;
- в консоли видно `*** Listening on default...`.

Проверка через rqinfo:

```bash
.venv\Scripts\rqinfo.exe
```

Ожидается хотя бы один воркер в очереди `default`.

### Остановка

- В терминале с `app/entrypoints/worker.py`: `Ctrl+C`.

---

## Telegram-бот (polling)

### Запуск (для разработки)

Самый надёжный способ — через `scripts/dev_run_all.py` (см. ниже).
Если нужно отдельно:

```bash
.venv\Scripts\python.exe -m app.entrypoints.bot
```

Проверено:
- бот поднимается, в консоли видно `Run polling for bot`;
- при `/start` в Telegram бот отвечает и логирует события в `logs/bot.log`.

**Важно:** нельзя запускать `app/entrypoints/bot.py` несколько раз параллельно — Telegram
возвращает `TelegramConflictError: terminated by other getUpdates request`.

### Остановка

- В терминале с `app/entrypoints/bot.py`: `Ctrl+C`.

---

## Dev-оркестратор: `scripts/dev_run_all.py` (backend + worker + bot)

Особенность (проверено): перед запуском `app/entrypoints/bot.py` скрипт пытается остановить другие
процессы бота (в том же venv/проекте), чтобы не ловить `TelegramConflictError`.

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
- `logs/worker*.log` — работа воркера, исключения в задачах.
- `logs/alerts.jsonl` / `logs/alerts.csv` — автоматические алерты по ERROR/CRITICAL.
- `logs/metrics.jsonl` / `logs/metrics.csv` — метрики времени/ошибок (`http_request`, `worker_job`).
- `logs/llm_costs.csv` — стоимость LLM по заявкам (заполняется после
  успешного вызова LLM, даже если документ не признан накладной).
- `logs/llm_costs_summary.json` — накопительные итоги по стоимости (USD/RUB).

---

## Операционные скрипты (наблюдаемость)

```bash
# сводка по метрикам за 24 часа
.venv\Scripts\python.exe scripts\metrics_report.py --hours 24

# архивирование старых логов
.venv\Scripts\python.exe scripts\archive_logs.py --days 7
```

---

## Отладка по коду заявки / коду события

- Короткий код заявки (5 цифр) показывается пользователю в ответе
  бота. Для диагностики:

```bash
.venv\Scripts\python.exe scripts\diagnose_request.py 48291
```

- Для чисто ботовых ошибок пользователю показывается короткий код (4 цифры, формат `Код: 4xxx`).
  В логах сохраняются и короткий код, и внутренний `BOT_*` код.
- Поиск делаем по `event_short` или `event_code` в `logs/mailbox/*.jsonl` и `logs/bot.log`.
- Полный справочник соответствий: `docs/BOT_EVENT_CODES.md`.
