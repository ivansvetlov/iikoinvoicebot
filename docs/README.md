# Telegram bot + backend РґР»СЏ РЅР°РєР»Р°РґРЅС‹С… -> iiko

## Р§С‚Рѕ РІР°Р¶РЅРѕ СЃРµР№С‡Р°СЃ
- РўРѕС‡РєРё РІС…РѕРґР° РїСЂРёР»РѕР¶РµРЅРёСЏ РІС‹РЅРµСЃРµРЅС‹ РІ `app/entrypoints/`:
  - `app.entrypoints.main` (ASGI backend)
  - `app.entrypoints.worker`
  - `app.entrypoints.bot`
- Р”РѕРєСѓРјРµРЅС‚Р°С†РёСЏ РІ `docs/`.
- Р¤Р°Р№Р»С‹ РґРµРїР»РѕСЏ РІ `deploy/`.
- РЁР°Р±Р»РѕРЅ РѕРєСЂСѓР¶РµРЅРёСЏ РІ `config/config/.env.example`.

## Р‘С‹СЃС‚СЂС‹Р№ Р·Р°РїСѓСЃРє
1. РЎРєРѕРїРёСЂРѕРІР°С‚СЊ `config/config/.env.example` РІ `.env` Рё Р·Р°РїРѕР»РЅРёС‚СЊ Р·РЅР°С‡РµРЅРёСЏ.
2. РЈСЃС‚Р°РЅРѕРІРёС‚СЊ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё: `pip install -r requirements.txt`
3. Р—Р°РїСѓСЃС‚РёС‚СЊ backend: `uvicorn app.entrypoints.main:app --host 127.0.0.1 --port 8000`
4. Р—Р°РїСѓСЃС‚РёС‚СЊ worker: `python -m app.entrypoints.worker`
5. Р—Р°РїСѓСЃС‚РёС‚СЊ bot: `python -m app.entrypoints.bot`

## Docker
- Compose: `deploy/deploy/docker-compose.yml`
- deploy/Dockerfile: `deploy/deploy/Dockerfile`
- Nginx config: `deploy/deploy/nginx_bot.conf`

РџСЂРёРјРµСЂ:
```bash
docker compose -f deploy/deploy/docker-compose.yml up -d --build
```

## РќР°РІРёРіР°С†РёСЏ РїРѕ РґРѕРєСѓРјРµРЅС‚Р°С†РёРё
- `docs/ARCHITECTURE.md`
- `docs/DEV_SETUP.md`
- `docs/DEBUG.md`
- `docs/AGENT_HANDOFF.md`
- `docs/TODO.md`

