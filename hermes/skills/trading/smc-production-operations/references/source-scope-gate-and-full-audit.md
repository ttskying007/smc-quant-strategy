# Source-scope gate and full-audit handoff

## When a provider cache appears complete

Do not infer eligibility from a single-symbol check, a shard result, or a cache-file count. Before authorizing a source-local research branch:

1. Run the source-isolated integrity audit **without** `--symbol`, `--limit`, or sharding, so the canonical `*_latest.json` artifact represents the full provider universe.
2. Confirm `symbols == canonical_universe_count`, `passed == symbols`, and `failed == 0`.
3. Re-run the source-read gate with the same denominator via `--required-symbols`.
4. Record the provider's actual earliest intraday timestamp separately from cache completeness.

A previous single-symbol latest artifact can make a legitimate full cache look unauthorized. The remedy is a fresh unsharded full audit—not lowering the source-gate denominator.

## V536 evidence pattern

Sina's isolated `daily/weekly/m60/m15` audit passed for 5,528 symbols after a full unsharded run, and the partial same-source read gate then authorized research. Its 15-minute history nevertheless began around 2025-04, so it remained ineligible for 2023–2026 replay, full-market promotion, and cross-provider repair.

## Frontier decision

If a prior outcome-blind partial-range ontology fails its predeclared support gate, do not manufacture a successor from a different threshold, window, exit, or regime of that same object. Reconcile the completed ontology inventory first. A new branch requires an independent causal information dimension *and* a source scope that its intended conclusion can honestly support.

For a request for continuous research under an unavailable full-history contract, keep production `EMPTY_BOOK`/fail-closed and continue only source-health, coverage, and integrity monitoring. Reopen outcome research only when the stated source/date/universe contract is actually met.
