# ARCHITECTURE

## РљРѕРјРїРѕРЅРµРЅС‚С‹
- `app.entrypoints.main` вЂ” ASGI backend (FastAPI).
- `app.entrypoints.worker` вЂ” RQ worker.
- `app.entrypoints.bot` вЂ” Telegram bot (polling).
- `app/api.py` вЂ” HTTP endpoints (`/health`, `/process`, `/process-batch`, `/metrics/summary`, webhook).
- `app/tasks.py` вЂ” РѕР±СЂР°Р±РѕС‚РєР° Р·Р°РґР°С‡ РѕС‡РµСЂРµРґРё.
- `app/services/pipeline.py` вЂ” РѕСЃРЅРѕРІРЅРѕР№ РїР°Р№РїР»Р°Р№РЅ СЂР°СЃРїРѕР·РЅР°РІР°РЅРёСЏ Рё Р·Р°РіСЂСѓР·РєРё РІ iiko.

## РРЅС„СЂР°СЃС‚СЂСѓРєС‚СѓСЂР°
- Redis + RQ РґР»СЏ РѕС‡РµСЂРµРґРё.
- SQLAlchemy РґР»СЏ task store.
- Р›РѕРіРё/РјРµС‚СЂРёРєРё/Р°Р»РµСЂС‚С‹ С‡РµСЂРµР· `app/observability.py`.
- Р”РµРїР»РѕР№-С„Р°Р№Р»С‹ РІ `deploy/`:
  - `deploy/deploy/Dockerfile`
  - `deploy/deploy/docker-compose.yml`
  - `deploy/deploy/nginx_bot.conf`
- РљРѕРЅС„РёРіРё РІ `config/`:
  - `config/config/.env.example`

## РџРѕС‚РѕРє
1. Bot РѕС‚РїСЂР°РІР»СЏРµС‚ С„Р°Р№Р» РІ backend.
2. Backend РІР°Р»РёРґРёСЂСѓРµС‚ РІС…РѕРґ, СЃРѕС…СЂР°РЅСЏРµС‚ payload Рё СЃС‚Р°РІРёС‚ Р·Р°РґР°С‡Сѓ РІ RQ.
3. Worker РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚ Р·Р°РґР°С‡Сѓ С‡РµСЂРµР· pipeline.
4. Р РµР·СѓР»СЊС‚Р°С‚ СѓС…РѕРґРёС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ Рё (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ) РІ iiko.

