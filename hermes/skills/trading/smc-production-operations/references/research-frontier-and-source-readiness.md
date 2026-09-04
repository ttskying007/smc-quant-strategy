# Research-frontier closure and source-readiness pattern

## Purpose

Use when a strategy-research program has closed its pre-registered daily-bar hypotheses but a request calls for continuous iteration. The correct next step is a no-write validation of new-information readiness—not a parameter variant.

## Evidence pattern

1. Read the current hypothesis inventory and latest frozen replay. Record the concrete closure cause for every object: support shortfall, independent-oracle mismatch, economic failure, cross-year failure, or promotion-gate failure.
2. Define the new-data contract before any outcome read. For a full-market minute-SMC study, require one provider, canonical-universe coverage, full target dates, and exact slot audits (15m=16, 60m=4 per trading day).
3. Re-probe a representative instrument directly and record HTTP/source status, received start/end timestamps, and bar count.
4. Run the source scope gate. A source-local cache pass and an authorized full-universe research pass are distinct facts.
5. Keep source series separate. A partial modern source cannot fill older bars in a legacy provider series.

## Decision table

| Observation | Decision |
|---|---|
| Full source-local integrity but partial date range | Diagnostic-only; no cross-year/full-market replay or promotion |
| Full date range but incomplete canonical universe | Cached-subset diagnostic only; no full-market conclusion |
| New PIT source below declared availability coverage | Close source without outcome replay |
| Full, same-source universe/date/slot contract passes | Authorize a genuinely new outcome-blind ontology |
| Any prerequisite fails | Keep production fail-closed and state the exact reopening condition |

## Example of a valid blocked conclusion

A provider returning current 15-minute bars yet beginning after the required 2023 start date is healthy as a recent witness but not eligible for a 2023–2026 full-market research contract. Do not shorten the evaluation period after seeing that result; report the missing date interval and retain the empty book.
