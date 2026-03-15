# iikoServer: Mapping for Incoming Invoice Posting

_Updated: 2026-03-11_

## Goal
Define a production-safe mapping from recognized invoice data to `iikoServer` incoming invoice import payload and reduce manual corrections before posting to stock.

## Confirmed API Endpoints
- Incoming invoice import: `POST https://host:port/resto/api/documents/import/incomingInvoice`
- Outgoing invoice import (related flow): `POST https://host:port/resto/api/documents/import/outgoingInvoice`
- Response model: `documentValidationResult` (`valid`, `warning`, `errorMessage`, `additionalInfo`, `otherSuggestedNumber`)

## Current Project State
- Current upload path in code is browser automation (`Playwright`) via UI forms.
- Target path is direct `iikoServer` import payload for incoming invoices.
- Recommended transition: dual mode (`iikoServer` primary + UI fallback behind feature flag during rollout).

## Canonical OCR/LLM Item Model (input to mapper)
Required business fields for each line:
- `name`
- `quantity`
- `mass` (if present)
- `unit_price`
- `amount_without_tax`
- `tax_rate`
- `tax_amount`
- `amount_with_tax`

Important parsing nuances:
- Quantity and mass can appear in one column; unit parsing decides split.
- VAT can be per line or one common rate for the whole invoice.

## Header Mapping (`incomingInvoiceDto`)
| iiko field | Use | Source / rule |
| --- | --- | --- |
| `items.item[]` | required logically | Array of mapped invoice lines |
| `id` | read-only | Do not send on create |
| `conception` / `conceptionCode` | optional | From integration config (default concept) |
| `comment` | optional | Service comment (`request_id`, source file, parser mode) |
| `documentNumber` | recommended | Invoice number from document (or generated fallback) |
| `dateIncoming` | recommended | Invoice date (`dd.MM.yyyy`) |
| `invoice` | optional | Счет-фактура number (if available) |
| `defaultStore` | recommended | Target warehouse GUID |
| `supplier` | recommended | Supplier GUID |
| `dueDate` | optional | Payment due date |
| `incomingDate` | optional | External incoming date (`yyyy-MM-dd`) |
| `useDefaultDocumentTime` | optional | `false` by default |
| `status` | recommended | `NEW` (safe draft) or `PROCESSED` (auto-post) by policy |
| `incomingDocumentNumber` | optional | External supplier document number |
| `employeePassToAccount` | optional | Employee GUID if required by accounting flow |
| `transportInvoiceNumber` | optional | Transport waybill number |
| `linkedOutgoingInvoiceId` | read-only | Do not send |
| `distributionAlgorithm` | read-only | Do not send |

## Line Mapping (`incomingInvoiceItemDto`)
| iiko field | Use | Source / rule |
| --- | --- | --- |
| `num` | required by XSD | 1..N line index |
| `sum` | required by XSD | `amount_with_tax` (line total incl. VAT) |
| `product` / `productArticle` | required logically | From nomenclature resolver by name + supplier article; at least one must be present |
| `supplierProduct` / `supplierProductArticle` | optional | Supplier-side identifiers from invoice if available |
| `amount` | recommended | Quantity in product base unit |
| `actualAmount` | optional/recommended | Usually same as `amount` at posting time |
| `containerId` | optional | Packing/container GUID when invoice is in packs/boxes |
| `amountUnit` | optional | Base unit GUID when required by product setup |
| `price` | recommended | Unit price in base unit (incl. VAT if totals are VAT-inclusive) |
| `priceWithoutVat` | optional | Unit price in base unit excluding VAT |
| `vatPercent` | recommended | Line VAT rate (`tax_rate`) |
| `vatSum` | recommended | Line VAT amount (`tax_amount`) |
| `discountSum` | optional | Discount amount if explicitly present |
| `priceUnit` | optional | Price unit identifier from iiko dictionary |
| `store` | optional | Per-line store override (if not using `defaultStore`) |
| `producer` | optional | Producer/importer (if used in product card) |
| `customsDeclarationNumber` | optional | Customs declaration number |
| `code` | optional | Legacy/custom code (rare) |
| `actualUnitWeight` | optional | Not recommended as primary field (legacy/limited support) |
| `isAdditionalExpense` | read-only | Do not send |

## Conversion Rules for Quantity/Mass/Pack
1. Detect product base unit from nomenclature (`kg`, `l`, `pcs`, etc.).
2. If invoice is in packs (e.g., `10 упак`, `2 короб`), resolve conversion coefficient `k` to base unit.
3. Fill:
- `amount = quantity_in_packs * k` (base units)
- `price = pack_price / k` (base-unit price)
- `sum = amount_with_tax`
4. If no pack conversion is known, send as base unit directly and flag line for manual review.

## VAT Normalization Rules
1. If line VAT values exist: use line `tax_rate`, `tax_amount`, `amount_with_tax`.
2. If only invoice-level VAT rate exists:
- set same `vatPercent` for each line
- compute `vatSum` from line totals
3. If only invoice-level VAT amount exists:
- distribute VAT proportionally by line `amount_with_tax`
4. If VAT is missing entirely:
- send with `vatPercent` omitted and mark warning for manual verification.

## Idempotency and Safety
Use deterministic external id:
- `external_key = supplier + documentNumber + dateIncoming + total + line_count`

Before import:
- check local processed registry (`request_id` + `external_key`)
- block duplicate post unless explicit override

Posting policy:
1. Default: import as `NEW` (draft), show summary, then confirm posting.
2. Optional auto-post mode: send `PROCESSED` when confidence and validations are green.

## Validation Gates Before API Call
Hard fail:
- Empty item list
- Missing product resolution for any line
- Missing mandatory line fields (`num`, `sum`)

Soft warnings:
- Missing VAT details
- Unknown pack conversion
- Large mismatch between `unit_price * quantity` and totals

## Implementation Plan (recommended)
1. Add `iikoServer` client module (separate from UI automation).
2. Add mapper layer: `InvoiceItem -> incomingInvoiceItemDto`.
3. Add reference-data cache: products, suppliers, stores, units, containers.
4. Add dry-run mode returning final XML/JSON payload preview.
5. Enable dual-run comparison (UI vs API) on pilot accounts.
6. Switch default to API path after stable error rate window.

## Sources
- https://ru.iiko.help/articles/#!api-documentations/zagruzka-i-redaktirovanie-prikhodnoy-nakladnoy
- https://ru.iiko.help/articles/#!api-documentations/zagruzka-i-redaktirovanie-raskhodnoy-nakladnoy
- https://ru.iiko.help/articles/#!api-documentations/iikoserver-api
