# PIT event source retry and pagination gate

## Use

Apply when a stratified pilot of a timestamped public-announcement source passes but the first canonical-universe coverage run fails due to request reliability or pagination, before declaring the information dimension unavailable.

## Distinguish failure classes

- A successful pilot proves endpoint semantics and timestamp fields, not canonical coverage.
- A first full-universe failure with incomplete HTTP success or capped page counts is a **transport/pagination qualification failure**, not evidence that events do not exist.
- Do not define an event-to-price/SMC ontology, read price/outcomes, or run a replay until the source-only coverage contract passes.

## Minimal recovery pattern

1. Preserve the fixed source contract: provider, universe, date range, metadata-only fields, and `same_day_execution_forbidden`.
2. Lower worker count when the full-universe pass shows transient request failures; use bounded retries.
3. Raise the per-symbol page ceiling if any symbol is marked truncated. Record both worker count and page cap in the report.
4. First run one real-symbol probe at the new page cap, asserting: HTTP success, no truncation, and nonempty publication timestamps for classified events.
5. Re-run the canonical-universe **metadata-only** audit. The pass requires at least 95% HTTP success, zero truncated symbols, and complete timestamps for every classified event.
6. Only after that pass, freeze one event ontology and proceed to outcome-blind identities → independent Oracle → one strict T+1 replay.

## Prohibited shortcuts

- Do not treat failed requests as no-event symbols.
- Do not lower the coverage denominator to successful requests.
- Do not use same-day announcement data for that day's execution.
- Do not fill gaps with a second provider or combine metadata with price/outcome data during qualification.
