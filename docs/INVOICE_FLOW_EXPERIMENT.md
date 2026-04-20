# Invoice Flow Experiment

This module adds a standalone flow switcher for invoice item post-processing.

Current production path is unchanged:
- parse invoice
- validate invoice
- upload to iiko

The new code is isolated in `app/services/invoice_flow/` and can be used for A/B checks.

## Modes

- `legacy`: keep current behavior, no modular suggestions.
- `shadow`: compute modular suggestions, but keep legacy output.
- `modular`: apply modular resolver output.

`INVOICE_FLOW_MODE` controls the default mode value.
`INVOICE_FLOW_ENABLE_UNIT_CONVERSION` toggles conversion logic.
`INVOICE_FLOW_ENABLE_CATALOG_MATCH` toggles catalog matching logic.

## Scope of modular resolver (v0 skeleton)

- unit normalization (`шт`, `уп`, `мл`, `л`, `г`, `кг`)
- direct conversion between compatible units
- inferred pack-size conversion from item name (`1л`, `500 мл`, `0.5 кг`)
- optional catalog match by normalized item name

## Example usage (standalone)

```python
from app.schemas import InvoiceItem
from app.services.invoice_flow import InvoiceFlowRunner

items = [InvoiceItem(name="Сироп Ваниль 1л", unit_measure="шт", supply_quantity=2)]
runner = InvoiceFlowRunner(mode="shadow")
result = runner.execute(items)
print(result.mode, result.changed_rows, len(result.suggestions))
```

## Notes

- This module is intentionally not wired into `InvoicePipelineService` yet.
- Integration can be done later behind the same mode flag for safe rollout.
