# Branch Plan: Optimization of Recognition Wait Time

Date: 2026-04-23  
Scope: separate branch only (do not mix into current working branch)

## Why this is needed

On problematic photos/invoices we spend too much time in chained LLM retries.
Observed on 2026-04-22:

- `20260422_121329_530_6106711925` -> ~52s (`worker_job.duration_ms=52071`)
- `20260422_181426_177_6106711925` -> ~86s (`worker_job.duration_ms=86582`)
- `20260422_140827_877_6106711925` -> ~131s (`worker_job.duration_ms=131135`)

For `20260422_140827_877_6106711925` logs show repeated truncation retries and multiple LLM passes:

- output tokens seen in one pipeline cycle: `1053`, `3200`, `996`
- repeated `Retrying LLM call with larger max_output_tokens due to truncation`
- debug snapshot: `tmp/llm_debug/20260422_141004_481_bad_function_json_20260422_140816_078168_260d16cd_invoice_photo.jpg.json`

## Current baseline (as-is)

In `app/services/pipeline.py`:

- `LLM_MAX_OUTPUT_TOKENS = 1000`
- `LLM_MAX_OUTPUT_TOKENS_RETRY = 3200`
- On `incomplete_details.reason == "max_output_tokens"` we retry once with larger cap.
- In addition to this, pipeline may run extra LLM passes for quality fixes:
  - `HEADER_NUMBER_HINT`
  - `REPEAT_VALUE_HINT`
  - `QUANTITY_HINT`
  - `CONSISTENCY_HINT`
- For image bad JSON/tool-call issues, `_run_llm_pass` can do rescue attempts.

Result: one request may trigger several LLM calls even without explicit user retry.

## Expected benefit from optimization

If we cap cascading retries and choose better initial output budget:

- lower p95 latency for heavy docs (target improvement: from 52-131s down to ~20-60s on same class)
- lower cost on pathological cases (remove repeated full calls caused only by truncation loops)
- more predictable user UX (fewer "long tail" waits)

## Main risks

- quality regression on bad scans (fewer salvage attempts -> more `llm_garbage` / incomplete extraction)
- false-negative invoice recognition on borderline photos
- if start budget is too high globally: potential higher token spend on normal docs
- complexity risk: too many dynamic rules can become hard to debug

## Branch implementation strategy

### 1) Add bounded retry budget (hard guardrails)

Introduce request-level budget (env-configurable):

- max total LLM calls per recognition
- max truncation retries per recognition
- max extra quality-repair passes
- max LLM wall-time budget per recognition

When budget is exhausted: stop new retries, return controlled user-facing result/warning.

### 2) Dynamic initial `max_output_tokens` (instead of fixed 1000 for all)

Compute start cap from document complexity:

- estimated row count (`_estimate_rows`)
- extracted text length
- source type (image/pdf/text)

Rule should be simple and deterministic (no "smart magic" first iteration).

### 3) Controlled truncation policy

Replace blind growth with bounded step policy:

- attempt #1 with dynamic start cap
- at most one controlled bump
- no unbounded repeat through chained quality passes

### 4) Retry gating for quality passes

Run header/repeat/qty/consistency re-prompts only if:

- there is remaining retry budget, and
- anomaly confidence is high enough, and
- expected gain > expected added latency

### 5) Better observability

Add structured metrics fields:

- `llm_calls_total`
- `llm_truncation_retries`
- `llm_quality_retries`
- `llm_budget_stop_reason`
- `llm_duration_ms_total`

This is required to tune thresholds safely.

## Initial threshold proposal (starting point for branch)

- `MAX_LLM_CALLS_PER_REQUEST = 4`
- `MAX_TRUNCATION_RETRIES = 1`
- `MAX_QUALITY_RETRIES = 2`
- `MAX_LLM_TIME_BUDGET_SEC = 35`

Dynamic start cap draft:

- small docs: `1200`
- medium docs: `1800`
- large docs: `2600`

One bump rule:

- `next_cap = min(start_cap + 1200, 3600)`

Note: these are startup values for branch experiments, not final production constants.

## Test matrix for branch

Mandatory regression set:

- `20260422_140827_877_6106711925` (131s case)
- `20260422_181426_177_6106711925` (86s case)
- `20260422_121329_530_6106711925` (52s case)
- old overflow-pattern cases from local logs:
  - `20260404_210103_049___________`
  - `20260404_221041_190___________`
  - `20260405_011105_945___________`

Success criteria:

- no increase of critical parse failures on control set
- p95 latency down for problematic cases
- no multi-truncation cascades without budget signal
- visible reason codes when budget stops retries

## Out of scope for this branch

- business rules for units/category mapping
- UI redesign of review flow/buttons
- iiko stock posting semantics

This branch is only about recognition wait optimization and retry economics.

## Rollback plan

Keep all new limits behind env flags.

If quality drops:

- disable dynamic cap
- fallback to previous fixed behavior by config
- keep new metrics for postmortem
