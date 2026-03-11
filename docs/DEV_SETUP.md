# DEV_SETUP

РџРѕРІС‚РѕСЂСЏРµРјС‹Р№ Р»РѕРєР°Р»СЊРЅС‹Р№ СЃС†РµРЅР°СЂРёР№ Р·Р°РїСѓСЃРєР° СЃ РЅРѕРІРѕР№ СЃС‚СЂСѓРєС‚СѓСЂРѕР№ РїСЂРѕРµРєС‚Р°.

## 1) РџРѕРґРіРѕС‚РѕРІРєР°
1. РЎРєРѕРїРёСЂСѓР№С‚Рµ `config/config/.env.example` РІ `.env`.
2. Р—Р°РїРѕР»РЅРёС‚Рµ РјРёРЅРёРјСѓРј: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `REDIS_URL`.
3. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
4. Р—Р°РїСѓСЃС‚РёС‚Рµ Redis.

## 2) Р—Р°РїСѓСЃРє РєРѕРјРїРѕРЅРµРЅС‚РѕРІ
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

## 3) РџСЂРѕРІРµСЂРєР°
```powershell
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"
.\.venv\Scripts\python.exe scripts\dev_status.py
```

## 4) Р›РѕРіРё
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

