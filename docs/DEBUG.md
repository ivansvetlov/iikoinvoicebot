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

## iikoServer RMS smoke (2026-03-16)
```powershell
.\.venv\Scripts\python.exe scripts\iiko_server_smoke.py `
  --base-url "https://840-786-070.iiko.it" `
  --username "user" `
  --password "user#test"
```

Итог:
- reachability: `PASS`
- auth: `PASS` через `form_login_pass_sha1` (token в plain text)
- import probe: `PASS` по доступности endpoint (HTTP 400 validation response)

Технические выводы:
- `/resto/api/auth` для данного стенда требует `application/x-www-form-urlencoded`.
- Рабочий формат auth: `login=<user>`, `pass=<sha1(password)>`.
- Для вызовов import токен должен передаваться через query-параметр `key`, а не только через `Authorization` header.
- Текущий probe payload специально минимальный и сейчас валидируется как некорректный по DTO (ожидаемо на этапе smoke).

Артефакт отчета:
- `logs/iiko_smoke_last.json`
