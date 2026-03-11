# DEBUG

Проверенные команды диагностики для текущего layout.

## Backend
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.entrypoints.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"
```

## Worker
```powershell
.\.venv\Scripts\python.exe -m app.entrypoints.worker
.\.venv\Scripts\rqinfo.exe
```

## Bot
```powershell
.\.venv\Scripts\python.exe -m app.entrypoints.bot
```

## Общая проверка
```powershell
.\.venv\Scripts\python.exe scripts\dev_status.py
.\.venv\Scripts\python.exe scripts\metrics_report.py --minutes 60
```

## Логи
- `logs/backend.log`
- `logs/worker.log`
- `logs/bot.log`
- `logs/errors.log`
- `logs/alerts.jsonl`
- `logs/metrics.jsonl`
