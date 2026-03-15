# DEV_SETUP

Повторяемый локальный сценарий запуска с новой структурой проекта.

## 1) Подготовка
1. Скопируйте `config/config/.env.example` в `.env`.
2. Заполните минимум: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `REDIS_URL`.
3. Установите зависимости:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
4. Запустите Redis.

## 2) Запуск компонентов
Backend:
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.entrypoints.main:app --host 127.0.0.1 --port 8000
```

Worker:
```powershell
.\.venv\Scripts\python.exe -m app.entrypoints.worker
```

Bot:
```powershell
.\.venv\Scripts\python.exe -m app.entrypoints.bot
```

## 3) Проверка
```powershell
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"
.\.venv\Scripts\python.exe scripts\dev_status.py
```

## 4) Логи
- `logs/backend.log`
- `logs/worker.log`
- `logs/bot.log`
- `logs/errors.log`
- `logs/alerts.jsonl`
- `logs/metrics.jsonl`

## 5) Docker
```powershell
docker compose -f deploy/deploy/docker-compose.yml up -d --build
```

