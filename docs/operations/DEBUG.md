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

PyCharm **«0. all»** = этот скрипт.

Поведение (2026-06):
- lock `tmp/dev_run_all.lock` — один оркестратор; stale lock снимается автоматически;
- pre-kill всех процессов проекта: `dev_run_all`, uvicorn (`app.api:app`), worker, bot;
- по умолчанию всегда свежий backend (без `backend already up, skipping`);
- `--reuse-backend` — не трогать uvicorn, если `/health` уже OK;
- `--force` — заменить работающий `dev_run_all`;
- shutdown через `taskkill /T /F` на Windows.

### Запуск всех компонент одной командой

```bash
.venv\Scripts\python.exe scripts\dev_run_all.py
.venv\Scripts\python.exe scripts\dev_run_all.py --force
.venv\Scripts\python.exe scripts\dev_run_all.py --reuse-backend
```

Проверено:
- скрипт последовательно запускает backend и ждёт `/health` (или переиспользует с `--reuse-backend`);
- затем запускает worker и бота;
- в случае ошибки на любом шаге пишет `ERROR` и останавливает дочерние процессы.

После успешного старта показывает PID'ы и ждёт `Ctrl+C` для остановки
всех процессов.

### Ручная зачистка (если зоопарк уже есть)

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'PycharmProjects\\PythonProject' -and
                 $_.CommandLine -match 'dev_run_all|uvicorn|entrypoints\.(bot|worker)' } |
  ForEach-Object { taskkill /PID $_.ProcessId /T /F }
Remove-Item -Force tmp\dev_run_all.lock -ErrorAction SilentlyContinue
```

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

## Grok Telegram bridge (experimental)

Отдельный бот (`GROK_BRIDGE_BOT_TOKEN`), не invoice bot.

```bash
.venv\Scripts\python.exe -m experiments.grok_telegram_bridge
```

Метапромпт: `experiments/grok_telegram_bridge/agents/METAPROMPT.md` (авто `--rules`).

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
- Полный справочник соответствий: `docs/operations/BOT_EVENT_CODES.md`.
