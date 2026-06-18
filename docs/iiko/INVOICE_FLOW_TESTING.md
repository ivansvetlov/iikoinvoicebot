# Invoice Flow Testing

## Current mode

- `INVOICE_FLOW_MODE=modular`
- `INVOICE_FLOW_ENABLE_UNIT_CONVERSION=true`
- `INVOICE_FLOW_ENABLE_LLM_FALLBACK=true`
- `INVOICE_FLOW_LLM_PROMPT_FORK_PATH=prompts/invoice_unit_resolution_fork.txt`
- `INVOICE_FLOW_OWNER_RULES_PATH=data/invoice_flow_owner_rules.json`
- iiko auto-create works without `AUTO` prefix in product names.

## Restart required

After `.env` changes restart backend + worker + bot:

```powershell
.\.venv\Scripts\python.exe scripts\dev_run_all.py
```

## What to test

1. Send invoice with count-based rows like:
   - `Сироп ... 1л ... 3 шт`
   - `Кофе ... 1кг ... 2 шт`
2. Run request diagnostic:

```powershell
python scripts/diagnose_request.py <request_code>
```

3. Open payload in requests log:
   - `logs/requests/<request_id>.json`

Check each converted row:
- `unit_measure` changed to `ml` or `g`
- `unit_amount` and `supply_quantity` contain converted value
- `extras.flowConversionReason` is present
- optional `extras.flowOwnerRule` if owner rule matched

4. In iiko, verify created nomenclature names:
- no `AUTO ` prefix should be added.

## New UX before posting to iiko

After recognition, `✅ Оприходовать` now opens a mandatory review step:
- shows item units preview (first 12 rows),
- shows units loaded from iiko,
- allows `✏ Редактировать` -> item -> `Ед. изм.`,
- has `🔄 Обновить ед. изм.` to refresh iiko unit list,
- only after that use `✅ Подтвердить оприходование`.

All edits are persisted to `logs/requests/<request_id>.json`, so `/iiko-upload-request`
and repeated posting use edited units/values.

## End-to-end scenario for current task

1. Full iiko cleanup (stocks + products to zero):

```powershell
python scripts/iiko_reset_stock.py --base-url <IIKO_API_BASE_URL> --login <IIKO_LOGIN> --password <IIKO_PASSWORD> --apply --delete-products
```

2. Re-post a previously recognized request by code (without re-OCR):
- in Telegram press `✅ Оприходовать` on recognized request
- or call backend `/iiko-upload-request` with saved `request_id`.

3. Check converted rows in response/request payload:
- piece-based liquids should become `ml` (`unit_measure=ml`)
- piece-based solids should become `g` (`unit_measure=g`)
- both `unit_amount` and `supply_quantity` should contain converted value
- `extras.flowConversionReason` should exist (`piece_to_volume_conversion`, `piece_to_mass_conversion`, etc.)

4. Verify iiko incoming invoice:
- document created with status `PROCESSED` (or configured status)
- amounts are posted in converted units (no accidental `шт` for gram/ml stock items).

## Owner rules

File: `data/invoice_flow_owner_rules.json`

Example:

```json
{
  "rules": [
    {
      "pattern": "(?i)кофе",
      "target_unit": "g",
      "piece_mass_g": 1000
    },
    {
      "pattern": "(?i)молоко",
      "target_unit": "g",
      "density_g_per_ml": 1.03,
      "piece_volume_ml": 1000
    }
  ]
}
```

Fields:
- `pattern`: regex for item name (required)
- `target_unit`: `g` / `kg` / `ml` / `l` (optional)
- `piece_mass_g`: mass per 1 pc/pack (optional)
- `piece_volume_ml`: volume per 1 pc/pack (optional)
- `density_g_per_ml`: density for mass-volume conversion (optional)

Notes:
- if `unit_measure` is missing but rule defines `piece_mass_g` / `piece_volume_ml`, row is treated as piece-based (`pcs`) and converted.
- for piece-based rows resolver now prefers `unit_amount` over `supply_quantity`.
- for ambiguous rows without deterministic conversion, LLM fallback can return `convert_to_mass|convert_to_volume|keep_pieces` and writes decision into `extras.flowLlmDecision`.

## Prompt fork for tests

Prompt file used by LLM fallback:
- `prompts/invoice_unit_resolution_fork.txt`

You can fork this prompt per environment via:
- `INVOICE_FLOW_LLM_PROMPT_FORK_PATH=/abs/or/relative/path.txt`
