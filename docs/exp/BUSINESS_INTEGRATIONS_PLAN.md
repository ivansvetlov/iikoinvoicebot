# Business Integration Plan in iiko Ecosystem

_Updated: 2026-03-11_

## Product Positioning
Core product is not "OCR for invoices".  
Core product is a procurement and margin control layer for restaurant groups on top of iiko.

## Strategic Direction
1. Start from invoice ingestion and stock posting automation.
2. Convert document flow into margin decisions and procurement controls.
3. Expand to network-level operating system (multi-store, multi-supplier, multi-brand).

## Non-Trivial Product Modules
| Module | Business value | Data used | Monetization model |
| --- | --- | --- | --- |
| Invoice-to-Stock Autopilot | Reduce labor and posting errors | Invoices, iiko stock docs, nomenclature | Per location + per posted document tier |
| Supplier Reliability Score | Lower hidden losses from delays/short-ships | Invoices, accepted qty, delivery dates, claim history | Advanced analytics add-on |
| Purchase Price Drift Radar | Protect gross margin via early alerts | Historical purchase prices, tech cards, menu sales | Margin control package |
| Recipe Cost Autoreconciliation | Keep food cost accurate without manual recalculation | Tech cards, incoming prices, yields, write-offs | Per brand/per month |
| Claim Assistant (auto discrepancy workflow) | Recover money from supplier mismatches | Invoice vs accepted qty vs stock movements | Value-share on recovered claims |
| Smart Substitution Engine | Prevent stop-sales by approved item substitutions | Nomenclature links, supplier catalogs, menu dependency graph | Enterprise package |
| Working Capital Optimizer | Improve cash cycle (DPO, payment windows) | Due dates, payable schedule, purchase seasonality | Finance analytics add-on |
| Cross-Store Procurement Hub | Consolidate orders and negotiate better terms | Multi-store demand, supplier matrix, logistics costs | HQ package per legal entity |

## Priority Roadmap
### 0-3 months (land and prove)
- Stable incoming invoice API posting (`iikoServer`) with idempotency.
- Supplier and SKU normalization layer.
- Basic discrepancy log (invoice vs accepted).
- KPI dashboard: posting speed, correction rate, prevented duplicates.

### 3-6 months (margin control)
- Purchase price drift alerts by key ingredients.
- Tech card cost impact view (what changed margin and why).
- Store-level and network-level variance analytics.
- Rule engine for auto-approval vs manual hold.

### 6-12 months (platform phase)
- Claim Assistant with semi-automatic supplier disputes.
- Smart substitutions integrated with menu/recipe constraints.
- Predictive reorder recommendations by demand + shelf-life.
- Multi-entity procurement cockpit for HQ.

## Integration Priorities in iiko Context
1. Incoming/Outgoing inventory documents (stock truth).
2. Nomenclature and units/containers (normalization base).
3. Suppliers and contracts (commercial layer).
4. Tech cards and dish cost (margin layer).
5. Sales and write-off events (closed-loop economics).

## Operational KPIs
| KPI | Baseline issue | Target after rollout |
| --- | --- | --- |
| Time from invoice receipt to stock posting | High manual latency | < 5 min for standard invoices |
| Manual correction rate | Frequent field edits | < 10% of lines |
| Duplicate posting incidents | Costly accounting errors | Near zero with idempotency |
| Unexplained food cost spikes | Detected late | Same-day alerting |
| Supplier discrepancy recovery | Usually unmanaged | Tracked and monetized recovery |

## Packaging for Go-to-Market
1. `Ops`: Posting automation + validation.
2. `Ops + Margin`: Price drift + recipe impact analytics.
3. `Enterprise`: Supplier scorecards, claims, cross-store optimization.

## Notes for Current Project
- Keep current UI automation as fallback until `iikoServer` path is stable.
- Treat mapping quality and nomenclature resolution as core moat.
- Build every new feature around measurable P&L effect, not feature count.

## External Context Sources
- https://ru.iiko.help/articles/#!api-documentations/iikoserver-api
- https://store.iiko.ru/
- https://store.iiko.ru/connectors
