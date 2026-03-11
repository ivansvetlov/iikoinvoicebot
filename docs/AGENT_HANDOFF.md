# Handoff: С‡С‚Рѕ СЃРґРµР»Р°РЅРѕ РІ РїСЂРѕРµРєС‚Рµ Рё РіРґРµ СЃРјРѕС‚СЂРµС‚СЊ (РґР»СЏ СЃР»РµРґСѓСЋС‰РµРіРѕ Р°РіРµРЅС‚Р°)

> Р¦РµР»СЊ СЌС‚РѕРіРѕ С„Р°Р№Р»Р° вЂ” С‡С‚РѕР±С‹ РЅРѕРІС‹Р№ Р°РіРµРЅС‚/СЂР°Р·СЂР°Р±РѕС‚С‡РёРє Р·Р° 10вЂ“15 РјРёРЅСѓС‚ РїРѕРЅСЏР» С‚РµРєСѓС‰РµРµ СЃРѕСЃС‚РѕСЏРЅРёРµ РїСЂРѕРµРєС‚Р°, СЂРµС€РµРЅРёСЏ Рё РіРґРµ РёСЃРєР°С‚СЊ РїСЂРёС‡РёРЅС‹ РѕС€РёР±РѕРє.

## 0) Р“Р»Р°РІРЅС‹Рµ РїСЂР°РІРёР»Р°
- РћСЃРЅРѕРІРЅС‹Рµ РїСЂР°РІРёР»Р° РґР»СЏ Р°РіРµРЅС‚РѕРІ/СЂР°Р·СЂР°Р±РѕС‚С‡РёРєРѕРІ: `docs/AGENTS.md` (РєРѕСЂРµРЅСЊ РїСЂРѕРµРєС‚Р°).
- РџСЂРѕРІРµСЂРµРЅРЅС‹Рµ РєРѕРјР°РЅРґС‹ Р·Р°РїСѓСЃРєР°/РґРёР°РіРЅРѕСЃС‚РёРєРё: `docs/DEBUG.md`.

## 0) Р’Р°Р¶РЅРѕ РїСЂРѕ СЃРµРєСЂРµС‚С‹
- **РќРµР»СЊР·СЏ РєРѕРјРјРёС‚РёС‚СЊ**: `.env`, `github_ssh_*`, РїР°РїРєРё `logs/`, `data/`, `tmp/`, `.venv/`.
- Р”Р°РјРї `dialogue_dump.jsonl` СЃРѕРґРµСЂР¶РёС‚ РёСЃС‚РѕСЂРёСЋ Рё РїРѕС‚РµРЅС†РёР°Р»СЊРЅРѕ СЃРµРєСЂРµС‚С‹, РїРѕСЌС‚РѕРјСѓ РѕРЅ **РІ `.gitignore`**.

## 1) РђСЂС…РёС‚РµРєС‚СѓСЂР° (РєР°Рє С‚РµС‡С‘С‚ Р·Р°РїСЂРѕСЃ)
**Telegram в†’ Bot в†’ Backend в†’ Queue (Redis/RQ) в†’ Worker в†’ (LLM/OCR/РїР°СЂСЃРёРЅРі) в†’ (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ iiko) в†’ Telegram editMessage**

РљР»СЋС‡РµРІС‹Рµ РјРѕРјРµРЅС‚С‹:
- Backend **РЅРµ** РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚ С„Р°Р№Р» СЃРёРЅС…СЂРѕРЅРЅРѕ: `/process` Рё `/process-batch` РєР»Р°РґСѓС‚ Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ Рё РѕС‚РІРµС‡Р°СЋС‚ `status="queued"`.
- Worker (`app/tasks.py`) РІС‹РїРѕР»РЅСЏРµС‚ РѕР±СЂР°Р±РѕС‚РєСѓ Рё **СЂРµРґР°РєС‚РёСЂСѓРµС‚** СЃС‚Р°С‚СѓСЃРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РІ Telegram.

## 2) Р“РґРµ РіР»Р°РІРЅР°СЏ Р»РѕРіРёРєР°
- `app/services/pipeline.py` вЂ” РѕСЃРЅРѕРІРЅРѕР№ РїР°Р№РїР»Р°Р№РЅ:
  - РёР·РІР»РµС‡РµРЅРёРµ С‚РµРєСЃС‚Р°/РєРѕРЅС‚РµРЅС‚Р°;
  - РІС‹Р·РѕРІ LLM;
  - РІР°Р»РёРґР°С†РёСЏ СЂРµР·СѓР»СЊС‚Р°С‚Р°;
  - (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ) Р·Р°РіСЂСѓР·РєР° РІ iiko.
- `app/api.py` вЂ” FastAPI:
  - `/process` (РѕРґРёРЅ С„Р°Р№Р»), `/process-batch` (РЅРµСЃРєРѕР»СЊРєРѕ С„Р°Р№Р»РѕРІ);
  - СЃРѕС…СЂР°РЅСЏРµС‚ job РІ `data/jobs/<request_id>/` Рё РєР»Р°РґС‘С‚ Р·Р°РґР°С‡Сѓ РІ РѕС‡РµСЂРµРґСЊ.
- `app/tasks.py` вЂ” РІРѕСЂРєРµСЂ:
  - С‡РёС‚Р°РµС‚ payload, РІС‹Р·С‹РІР°РµС‚ pipeline, РїРёС€РµС‚ РІ Р‘Р” (TaskRecord), СЂРµРґР°РєС‚РёСЂСѓРµС‚ СЃРѕРѕР±С‰РµРЅРёРµ РІ Telegram.
- `app/bot/manager.py` вЂ” Р»РѕРіРёРєР° Telegram:
  - РїРѕРґРґРµСЂР¶РєР° С„РѕС‚Рѕ/РґРѕРєСѓРјРµРЅС‚РѕРІ;
  - media group (Р°Р»СЊР±РѕРј) в†’ `/process-batch`;
  - `/split` + `/done` СЂРµР¶РёРј РґР»СЏ СЃРєР»РµР№РєРё С‡Р°СЃС‚РµР№;
  - rate-limit/РёРґРµРјРїРѕС‚РµРЅС‚РЅРѕСЃС‚СЊ/Р»РѕРіРёСЂРѕРІР°РЅРёРµ СЃРѕР±С‹С‚РёР№.
- `app/bot/backend_client.py` вЂ” HTTPвЂ‘РєР»РёРµРЅС‚ РґР»СЏ `/process` Рё `/process-batch` (Р±РѕС‚ в†’ backend).
- `app/bot/file_storage.py` вЂ” С„Р°Р№Р»РѕРІРѕРµ С…СЂР°РЅРёР»РёС‰Рµ pending/split (bot side).
- `docs/ARCHITECTURE.md` вЂ” РєСЂР°С‚РєРёР№ РѕР±Р·РѕСЂ РјРѕРґСѓР»РµР№ Рё РїРѕС‚РѕРєРѕРІ.

## 3) Р§С‚Рѕ РґРѕР±Р°РІРёР»Рё РґР»СЏ СѓСЃС‚РѕР№С‡РёРІРѕСЃС‚Рё (РЅРµРіР°С‚РёРІРЅС‹Рµ РєРµР№СЃС‹)
### 3.1 User-friendly РѕС€РёР±РєРё + error_code
- Р’ API-РѕС‚РІРµС‚Р°С… РµСЃС‚СЊ `error_code` (РјР°С€РёРЅРѕС‡РёС‚Р°РµРјС‹Р№ РєРѕРґ), РїРѕ РЅРµРјСѓ Р±РѕС‚ РїРѕРєР°Р·С‹РІР°РµС‚ РїРѕРґСЃРєР°Р·РєРё.
- РћС€РёР±РєРё С„РѕСЂРјР°С‚РёСЂСѓСЋС‚СЃСЏ Р±РµР· СЃС‚РµРєС‚СЂРµР№СЃРѕРІ.

### 3.2 Р—Р°С‰РёС‚Р° РѕС‚ В«Р·Р°С†РёРєР»РёРІР°РЅРёСЏВ» LLM
РџСЂРёС‡РёРЅР° Р±Р°РіР°: LLM РјРѕР¶РµС‚ РЅР°С‡Р°С‚СЊ РїРѕРІС‚РѕСЂСЏС‚СЊ СЃС‚СЂРѕРєРё (РЅР°РїСЂРёРјРµСЂ, "РњР°СЃСЃР° Р±СЂСѓС‚С‚Рѕ" Рё РЅСѓР»Рё), СЂР°Р·РґСѓРІР°С‚СЊ РѕС‚РІРµС‚ РґРѕ Р»РёРјРёС‚Р° Рё РѕС‚РґР°РІР°С‚СЊ **РѕР±СЂРµР·Р°РЅРЅС‹Р№ JSON**.

РЎРґРµР»Р°РЅРѕ:
- `max_output_tokens` СѓРјРµРЅСЊС€РµРЅ РґРѕ **1000**;
- РІ function schema РѕРіСЂР°РЅРёС‡РµРЅС‹ `items` С‡РµСЂРµР· `maxItems` (СЃРј. `pipeline.py`);
- РґРѕР±Р°РІР»РµРЅ РґРµС‚РµРєС‚РѕСЂ РјСѓСЃРѕСЂР° (`llm_garbage` / `llm_bad_response`).

## 4) РљРѕРґС‹ Р·Р°СЏРІРѕРє: РґР»РёРЅРЅС‹Р№ request_id vs РєРѕСЂРѕС‚РєРёР№ РєРѕРґ
- Р’РЅСѓС‚СЂРµРЅРЅРёР№ `request_id` РґР»РёРЅРЅС‹Р№ Рё РЅСѓР¶РµРЅ СЃРёСЃС‚РµРјРµ (СѓРЅРёРєР°Р»СЊРЅРѕСЃС‚СЊ, РїР°РїРєРё jobs, Р‘Р”).
- РџРѕР»СЊР·РѕРІР°С‚РµР»СЋ РїРѕРєР°Р·С‹РІР°РµРј РєРѕСЂРѕС‚РєРѕ: **`HHMMSS_mmm`** (РЅР°РїСЂРёРјРµСЂ `000736_800`).

### Р•РґРёРЅС‹Р№ С„РѕСЂРјР°С‚ СЃРѕРѕР±С‰РµРЅРёР№
РЎРґРµР»Р°РЅРѕ С‚Р°Рє, С‡С‚РѕР±С‹ Р±РѕС‚ Рё РІРѕСЂРєРµСЂ С„РѕСЂРјР°С‚РёСЂРѕРІР°Р»Рё СЃРѕРѕР±С‰РµРЅРёСЏ РѕРґРёРЅР°РєРѕРІРѕ:
- `app/utils/user_messages.py`:
  - `short_request_code(request_id)`
  - `format_user_response(payload)`

## 5) Р”РёР°РіРЅРѕСЃС‚РёРєР° РїРѕ РєРѕРґСѓ Р·Р°СЏРІРєРё (СЃР°РјС‹Р№ РїРѕР»РµР·РЅС‹Р№ РёРЅСЃС‚СЂСѓРјРµРЅС‚)
РЎРєСЂРёРїС‚:
- `scripts/diagnose_request.py`

РћРЅ РїСЂРёРЅРёРјР°РµС‚:
- РїРѕР»РЅС‹Р№ request_id
- РєРѕСЂРѕС‚РєРёР№ РєРѕРґ (`000736_800`)
- РёР»Рё СЃС‚СЂРѕРєСѓ С†РµР»РёРєРѕРј (`РљРѕРґ Р·Р°СЏРІРєРё: 000736_800`)

Р РїРµС‡Р°С‚Р°РµС‚ + СЃРѕС…СЂР°РЅСЏРµС‚ РѕС‚С‡С‘С‚:
- `tmp/diagnose_<request_id>.json`

## 6) Veai workflows (РїРѕРґСЃРєР°Р·РєРё РІ IDE)
РЎРј. `.veai/workflows/`:
- `Р”РёР°РіРЅРѕСЃС‚РёРєР°_request_id.md`
- `Р РµРіСЂРµСЃСЃРёСЏ_СЃРјРѕСѓРє_С‡РµРє.md`
- `РћС‚РєР°С‚_С‡РµСЂРµР·_git_Р±РµР·РѕРїР°СЃРЅРѕ.md`

## 7) Git-РїСЂРѕС†РµСЃСЃ (РєР°Рє РЅРµ Р±РѕСЏС‚СЊСЃСЏ РѕС‚РєР°С‚РѕРІ)
- `main` вЂ” СЃС‚Р°Р±РёР»СЊРЅР°СЏ РІРµС‚РєР°.
- РўРµРі СЃС‚Р°Р±РёР»СЊРЅРѕР№ С‚РѕС‡РєРё: `stable-2026-03-09`.
- РўРµРєСѓС‰Р°СЏ СЂР°Р±РѕС‚Р°: РІРµС‚РєР° `feature/stage4-reliability-observability`.

## 8) РР·РІРµСЃС‚РЅС‹Рµ РїСЂРѕР±Р»РµРјС‹/Р·Р°РјРµС‚РєРё
- **Media group Р°Р»СЊР±РѕРј**: РµСЃР»Рё backend СЃРѕС…СЂР°РЅСЏРµС‚ С„Р°Р№Р»С‹ РїРѕ РѕРґРёРЅР°РєРѕРІРѕРјСѓ РёРјРµРЅРё, РІРѕР·РјРѕР¶РЅР° РїРµСЂРµР·Р°РїРёСЃСЊ. `/split` СЃРѕС…СЂР°РЅСЏРµС‚ СѓРЅРёРєР°Р»СЊРЅС‹Рµ РёРјРµРЅР° Рё РЅР°РґС‘Р¶РЅРµРµ.
- Р•СЃР»Рё РІРёРґРёС‚Рµ РјСѓСЃРѕСЂ РІСЂРѕРґРµ "РњР°СЃСЃР° Р±СЂСѓС‚С‚Рѕ" вЂ” СЌС‚Рѕ РїСЂРёР·РЅР°Рє С‚РѕРіРѕ, С‡С‚Рѕ РЅР° РІС…РѕРґ РїСЂРёС€Р»Р° С‡Р°СЃС‚СЊ С‚Р°Р±Р»РёС†С‹ Р±РµР· РєРѕРЅС‚РµРєСЃС‚Р° (РІРµСЂС‚РёРєР°Р»СЊРЅС‹Рµ РїРѕР»РѕСЃС‹). Р›СѓС‡С€Рµ С†РµР»СЊРЅС‹Р№ РєР°РґСЂ/ PDF.

## 9) РќРµРґР°РІРЅРёРµ РёР·РјРµРЅРµРЅРёСЏ (2026-03-10)
- РџРµСЂРµСЂР°Р±РѕС‚Р°РЅ pending-UX РІ Р±РѕС‚Рµ: РІРјРµСЃС‚Рѕ СЃРєСЂС‹С‚РѕРіРѕ С‚Р°Р№РјРµСЂР° вЂ” СЏРІРЅС‹Рµ РєРЅРѕРїРєРё "РћР±СЂР°Р±РѕС‚Р°С‚СЊ/Р”РѕР±Р°РІРёС‚СЊ РµС‰С‘", Рё СЏРІРЅС‹Р№ РІС‹Р±РѕСЂ СЂРµР¶РёРјР° РїСЂРё 2+ С„Р°Р№Р»Р°С…. Р¤Р°Р№Р»С‹: `app/bot/manager.py`, `app/bot/backend_client.py`, `app/bot/file_storage.py`.
- Р›РѕРі СЃС‚РѕРёРјРѕСЃС‚Рё LLM РїРµСЂРµРІРµРґС‘РЅ РІ append-only (Р±РµР· РїРµСЂРµС‡С‚РµРЅРёСЏ CSV). Р¤Р°Р№Р»: `app/services/pipeline.py`.
- `.env` С‡РёС‚Р°РµС‚СЃСЏ СЃ `utf-8-sig` РёР·-Р·Р° BOM; РґРѕР±Р°РІР»РµРЅС‹ СѓС‚РёР»РёС‚С‹ `scripts/check_bom.py` Рё `scripts/strip_bom.py`.
- РђСЂС…РёС‚РµРєС‚СѓСЂРЅС‹Р№ РѕР±Р·РѕСЂ РїРµСЂРµРЅРµСЃС‘РЅ РІ `docs/ARCHITECTURE.md`.
- Р”РѕР±Р°РІР»РµРЅ `.gitattributes` РґР»СЏ LF РІ СЂРµРїРѕР·РёС‚РѕСЂРёРё; Р»РѕРєР°Р»СЊРЅРѕ `core.autocrlf=false` СЂРµРєРѕРјРµРЅРґРѕРІР°РЅ РґР»СЏ С‡РёСЃС‚С‹С… РґРёС„С„РѕРІ.
- Р”РѕР±Р°РІР»РµРЅ `logs/llm_costs_summary.json` (РёС‚РѕРіРё LLM Р±РµР· РїРµСЂРµСЃС‡С‘С‚Р° CSV) + `scripts/llm_costs_rebuild.py` РґР»СЏ РїРµСЂРµСЃР±РѕСЂРєРё.
- РЈРїСЂРѕС‰С‘РЅ UX: СѓР±СЂР°РЅ СЂРµР¶РёРј `/multi`, РІ split РґРѕР±Р°РІР»РµРЅС‹ РєРЅРѕРїРєРё В«Р—Р°РІРµСЂС€РёС‚СЊ/Р”РѕР±Р°РІРёС‚СЊ РµС‰С‘/РћС‚РјРµРЅРёС‚СЊВ».
- `/start` С‚РµРїРµСЂСЊ РѕС‡РёС‰Р°РµС‚ pending/split Р±СѓС„РµСЂС‹, С‡С‚РѕР±С‹ РЅРµ С‚СЏРЅСѓС‚СЊ СЃС‚Р°СЂС‹Рµ С„Р°Р№Р»С‹.

РџСЂРѕРІРµСЂРєР°: Р·Р°РїСѓСЃС‚РёС‚СЊ `python -m app.entrypoints.bot`, РѕС‚РїСЂР°РІРёС‚СЊ 1 С„Р°Р№Р» Рё СѓР±РµРґРёС‚СЊСЃСЏ, С‡С‚Рѕ РїРѕСЏРІР»СЏРµС‚СЃСЏ СЏРІРЅР°СЏ РєР»Р°РІРёР°С‚СѓСЂР° "РћР±СЂР°Р±РѕС‚Р°С‚СЊ/Р”РѕР±Р°РІРёС‚СЊ РµС‰С‘"; РѕС‚РїСЂР°РІРёС‚СЊ 2 С„Р°Р№Р»Р° вЂ” СѓРІРёРґРµС‚СЊ РІС‹Р±РѕСЂ "РћР±СЉРµРґРёРЅРёС‚СЊ/Р Р°Р·РґРµР»СЊРЅРѕ".

---

### Р‘С‹СЃС‚СЂС‹Р№ С‡РµРє-Р»РёСЃС‚ РґР»СЏ РЅРѕРІРѕРіРѕ Р°РіРµРЅС‚Р°
1) РџСЂРѕС‡РёС‚Р°С‚СЊ СЌС‚РѕС‚ С„Р°Р№Р».
2) РћС‚РєСЂС‹С‚СЊ `pipeline.py`, РЅР°Р№С‚Рё РЅР°СЃС‚СЂРѕР№РєРё LLM (max_output_tokens/maxItems) Рё РґРµС‚РµРєС‚РѕСЂ РјСѓСЃРѕСЂР°.
3) РџСЂРё Р»СЋР±РѕР№ РїСЂРѕР±Р»РµРјРµ вЂ” РІР·СЏС‚СЊ РєРѕРґ Р·Р°СЏРІРєРё Рё Р·Р°РїСѓСЃС‚РёС‚СЊ `scripts/diagnose_request.py`.

## 10) Recent changes (2026-03-11)
- Improved image preprocessing for recognition: auto-crop white document area, autocontrast, upscale, unsharp mask.
  Files: `app/services/pipeline.py`.
- Default image model set to `gpt-4o` via `OPENAI_MODEL_IMAGE` to improve OCR-heavy accuracy.
- Increased cropped image upscale cap and sharpening; JPEG quality raised for better numeric legibility.
- Settings now ignore empty environment variables (`env_ignore_empty=True`) so `.env` values are not overridden by blank envs.
- If image parse looks like garbage or empty after preprocessing, the pipeline retries once with the raw image.
- Added stronger prompt guardrails to avoid placeholder/empty rows.
- Prompt now explicitly forbids semantic substitution of item names.
- Added garbage detection for many empty rows.
- Added optional OCR hint for images (pytesseract + system Tesseract). Flag: `ENABLE_IMAGE_OCR_HINT`.
- Added header-number leak detector (1..15 column index row) with prompt retry.
- If OCR text includes a header line with column numbers (1..15), it is passed as an alignment hint.
- Added repeated numeric column detector (e.g., same price/total across rows) with prompt retry.
- Updated `docs/BOT_COMMAND_MATRIX.md` with current UX behavior (single/multi/split/PDF).
- TODO: marked split-album aggregation as done.
- Synced docs: updated `docs/AGENTS.md`, `docs/DEV_SETUP.md`, `docs/ARCHITECTURE.md`, `docs/TESTCASES.md` to match current UX and run config usage.

## 11) Recognition focus: iiko target fields (2026-03-11)
- LLM schema now targets explicit item fields: `name`, `quantity`, `mass`, `unit_price`, `amount_without_tax`, `tax_rate`, `tax_amount`, `amount_with_tax`.
- Mapping: `quantity -> unit_amount`, `mass -> supply_quantity`, `amount_without_tax -> cost_without_tax`, `amount_with_tax -> cost_with_tax/total_cost`.
- Basic derivations added: compute missing `amount_with_tax`/`tax_amount`/`tax_rate` when possible.
- User-facing invoice formatting shows mass, sum Р±РµР· РќР”РЎ, РќР”РЎ %, РќР”РЎ СЃСѓРјРјР°, СЃСѓРјРјР° СЃ РќР”РЎ.
- Image preprocessing now attempts OCR-based header detection to crop above the table header with safe padding. If OCR is unavailable, it falls back to line-based grid detection (horizontal/vertical runs).
- Cropped images allow a larger upscale cap (`IMAGE_MAX_DIM_CROPPED`) to improve readability of small tables.
- Added `TESSERACT_CMD` config and auto-detection of common Windows install paths for OCR.
- Image model overrides: `OPENAI_MODEL_IMAGE` and optional `OPENAI_MODEL_IMAGE_FALLBACK` for stronger retries on OCR-heavy images.

## 12) Event codes centralization (2026-03-11)
- Р¤Р°Р№Р»С‹:
  - РґРѕР±Р°РІР»РµРЅ `app/bot/event_codes.py` (РµРґРёРЅС‹Р№ СЂРµРµСЃС‚СЂ `BOT_*` + helper С„РѕСЂРјР°С‚РёСЂРѕРІР°РЅРёСЏ);
  - РґРѕР±Р°РІР»РµРЅ `docs/BOT_EVENT_CODES.md` (РєР°РЅРѕРЅРёС‡РµСЃРєРѕРµ РѕРїРёСЃР°РЅРёРµ РєРѕРґРѕРІ Рё СЃС‚Р°С‚СѓСЃРѕРІ active/archive);
  - РѕР±РЅРѕРІР»РµРЅС‹ `app/bot/manager.py`, `docs/DEBUG.md`, `docs/README.md`, `docs/TODO.md`.
- РџРѕРІРµРґРµРЅРёРµ:
  - РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРµ СЃРѕРѕР±С‰РµРЅРёСЏ СЃ `РљРѕРґ СЃРѕР±С‹С‚РёСЏ: BOT_*` С„РѕСЂРјРёСЂСѓСЋС‚СЃСЏ С‡РµСЂРµР· РµРґРёРЅС‹Р№ helper (`append_event_code`);
  - Р°РєС‚РёРІРЅС‹Рµ РєРѕРґС‹ (`BOT_BACKEND_UNAVAILABLE`, `BOT_RATE_LIMIT`, `BOT_NO_PENDING`) СЃРѕР±СЂР°РЅС‹ РІ РѕРґРЅРѕРј РјРµСЃС‚Рµ;
  - `BOT_PENDING_TIMEOUT` Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅ РєР°Рє Р°СЂС…РёРІРЅС‹Р№ (РЅРµ СЌРјРёС‚РёС‚СЃСЏ СЃ РїРµСЂРµС…РѕРґР° РЅР° СЏРІРЅС‹Р№ pending UX).
- Р‘С‹СЃС‚СЂР°СЏ РїСЂРѕРІРµСЂРєР°:
  - `python -m compileall app\bot\event_codes.py app\bot\manager.py`
  - РѕС‚РєСЂС‹С‚СЊ `docs/BOT_EVENT_CODES.md` Рё СЃРІРµСЂРёС‚СЊ РєРѕРґС‹ СЃ `app/bot/event_codes.py`.

## 13) Stage 4 completed: reliability + observability (2026-03-11)
- Р¤Р°Р№Р»С‹:
  - РґРѕР±Р°РІР»РµРЅ `app/observability.py` (РµРґРёРЅРѕРµ Р»РѕРіРёСЂРѕРІР°РЅРёРµ, Р°Р»РµСЂС‚С‹, РјРµС‚СЂРёРєРё);
  - РґРѕР±Р°РІР»РµРЅС‹ `scripts/metrics_report.py`, `scripts/export_user_messages.py`;
  - РґРѕР±Р°РІР»РµРЅ `docs/BOT_MESSAGE_CATALOG.md`;
  - РѕР±РЅРѕРІР»РµРЅС‹ `app/api.py`, `app/tasks.py`, `app/entrypoints/bot.py`, `app/entrypoints/worker.py`, `app/config.py`, `config/.env.example`;
  - РѕР±РЅРѕРІР»РµРЅС‹ `docs/DEBUG.md`, `docs/DEV_SETUP.md`, `docs/ARCHITECTURE.md`, `docs/README.md`, `docs/TODO.md`;
  - СѓРґР°Р»РµРЅР° РјС‘СЂС‚РІР°СЏ РїР°РїРєР° `app/logs/`.
- РџРѕРІРµРґРµРЅРёРµ:
  - backend/worker/bot РїРёС€СѓС‚ Р»РѕРіРё С‡РµСЂРµР· РµРґРёРЅС‹Р№ observability-СЃР»РѕР№ РІ `logs/*.log` + РѕР±С‰РёР№ `logs/errors.log`;
  - РІРєР»СЋС‡РµРЅС‹ Р°Р»РµСЂС‚С‹ РІ `logs/alerts.jsonl` (c cooldown Рё optional Telegram С‡РµСЂРµР· `ALERTS_TELEGRAM_CHAT_ID`);
  - РІРєР»СЋС‡РµРЅ РјРѕРЅРёС‚РѕСЂРёРЅРі РІСЂРµРјРµРЅРё/РѕС€РёР±РѕРє РІ `logs/metrics.jsonl`, РґРѕСЃС‚СѓРїРµРЅ `/metrics/summary` Рё `scripts/metrics_report.py`;
  - РІСЃРµ С‡РµРєР±РѕРєСЃС‹ Р­С‚Р°РїР° 4 РѕС‚РјРµС‡РµРЅС‹ РєР°Рє РІС‹РїРѕР»РЅРµРЅРЅС‹Рµ РІ `docs/TODO.md`;
  - С‚РµРєСЃС‚С‹ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёС… СЃРѕРѕР±С‰РµРЅРёР№ РІС‹РЅРµСЃРµРЅС‹ РІ РѕС‚РґРµР»СЊРЅС‹Р№ РєР°С‚Р°Р»РѕРі `docs/BOT_MESSAGE_CATALOG.md` (РѕР±РЅРѕРІР»СЏРµС‚СЃСЏ СЃРєСЂРёРїС‚РѕРј).
- Р‘С‹СЃС‚СЂР°СЏ РїСЂРѕРІРµСЂРєР°:
  - `python -m compileall app\observability.py app\api.py app\\tasks.py app\\entrypoints\\bot.py app\\entrypoints\\worker.py scripts\metrics_report.py scripts\export_user_messages.py`
  - `curl "http://127.0.0.1:8000/metrics/summary?window_minutes=60"`
  - `python scripts\metrics_report.py --minutes 60`
  - `python scripts\export_user_messages.py`

## 14) Local iiko server docs cache (2026-03-11)
- Files:
  - added `iiko_server_docs/SOURCES.txt` (source URL list);
  - added `iiko_server_docs/README.md` (how to refresh/search cache);
  - added `scripts/cache_iiko_server_docs.ps1` (download HTML snapshots);
  - added `scripts/search_iiko_server_docs.ps1` (local grep helper).
- Behavior:
  - docs are cached in `iiko_server_docs/*.html` with summary in `INDEX.md`;
  - hash routes like `.../#!api-documentations/iikoserver-api` are resolved to direct fetch URLs.
- Quick check:
  - `powershell -ExecutionPolicy Bypass -File scripts\cache_iiko_server_docs.ps1`
  - `powershell -ExecutionPolicy Bypass -File scripts\search_iiko_server_docs.ps1 -Pattern "iikoserver"`

## 15) Stage 3 block: guardrails and OCR quality (2026-03-11)
- Files:
  - updated `app/services/pipeline.py` (stronger OCR/LLM guardrails, image preprocessing, schema alignment);
  - updated `app/utils/user_messages.py` (richer invoice output fields and request code in final message);
  - updated `requirements.txt` (added `pytesseract`);
  - updated `docs/BOT_COMMAND_MATRIX.md` (current UX behavior notes).
- Behavior:
  - pipeline now detects typical garbage LLM outputs more aggressively (repeats/zeros/header leakage/repeated numeric columns);
  - image flow includes OCR hints and retries/fallbacks to improve extraction stability on table invoices;
  - user-facing invoice message includes mass, VAT details and short request code.
- Quick check:
  - `python -m compileall app\services\pipeline.py app\utils\user_messages.py`
  - send one invoice image/pdf through bot and verify final message contains VAT/mass fields and request code;
  - verify no regressions in `/process` and worker task completion logs.

## 16) Repo hygiene sync (2026-03-11)
- Files:
  - added `scripts/cache_iiko_server_docs.ps1`;
  - added `scripts/search_iiko_server_docs.ps1`;
  - updated `docs/AGENT_HANDOFF.md`.
- Behavior:
  - local iiko docs scripts are now present in this branch (no doc/code drift);
  - both scripts resolve relative paths from repo root (`iiko_server_docs/...`) and work regardless of current shell directory;
  - for current active branch always trust `git status -sb` instead of static text in this file.
- Quick check:
  - `powershell -ExecutionPolicy Bypass -File scripts\search_iiko_server_docs.ps1 -Pattern "iikoserver"`



