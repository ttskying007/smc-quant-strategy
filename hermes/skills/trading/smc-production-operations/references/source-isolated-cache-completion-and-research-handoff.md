# Source-isolated cache completion and research handoff

## Why this exists

A cache can be internally complete while still being unsuitable for a claimed historical scope. Treat **cache completeness**, **source-local read authorization**, and **full-history/promotion authorization** as three separate decisions.

## Durable controller contract

For a resumable, source-isolated OHLCV cache:

1. Derive the canonical universe from a dated independent ledger, never from files already in the cache.
2. A symbol is complete only if the intersection of all required frames exists (`daily`, `weekly`, `m60`, `m15`). Recompute this intersection before every batch; never use one frame as a completion marker.
3. Write every frame atomically. A restart must revisit partial symbols rather than treating them as complete.
4. Run under a boot-enabled service with `Restart=always` (or equivalent supervisor), lock single-writer execution, persist batch state atomically, and use bounded exponential backoff after a failed batch.
5. Verify recovery by actually terminating the controller once and confirming a new PID continues the same missing set.
6. At completion, run both coverage and full source-local integrity audit automatically.

## Gate interpretation

- `SOURCE_ISOLATED_CACHE_PASS` plus 100% coverage against the declared canonical universe authorizes **same-source research only**.
- It does **not** authorize cross-provider substitution.
- It does **not** authorize a longer historical claim when the provider's minute range begins later than that claim. For example, a provider with 15m coverage beginning in 2025 may support a 2025+ research cohort but must remain blocked for a 2023–2026 conclusion and for production promotion.
- Gate readers should use the exact generated full audit artifact when present and otherwise the documented `*_latest.json` artifact. Do not fail closed merely because a nonexistent filename such as `*_full_latest.json` was assumed.

## Research handoff after completion

Before opening PnL:

1. Call the source-read gate with the exact source, scope, and required denominator.
2. Create a new outcome-blind seed generator that reads only one provider namespace.
3. State the provider-specific date range in every artifact and use support gates appropriate to that range; do not silently require unavailable years or pool source ranges.
4. Require independent Oracle equivalence before one frozen strict-T+1 replay.
5. Keep all cache, seed, Oracle, and replay work no-write until a separate production gate passes.

## Acceptance evidence

Keep: canonical ledger, coverage report, source-local audit, service state/restart proof, generator support report, and explicit `research_only=true` / `production_write=false` flags. Historical trades, current watchlists, and production registry must remain untouched during this path.

### Large-universe replay resource contract

For a full-universe source-local replay, process one symbol at a time and discard its raw bars, indexes, and aggregation tables before loading the next. Per-symbol serial-position rules remain equivalent; retaining every symbol's raw bars or sparse tables can exhaust memory and make a no-write audit fail operationally. Verify replay memory stays bounded while keeping source provenance and row-level audit output intact.

### Latest-artifact integrity

A diagnostic invocation scoped by `--symbol`, `--limit`, or an audit shard must write only a timestamped diagnostic artifact; it must never replace the source-wide `*_latest.json`. Before any source-read gate, verify that `*_latest.json` has the source-wide canonical count rather than a one-symbol probe count. If a complete controller state captures a verified full audit, restore the latest pointer only from that immutable controller record, then re-run the read gate.
