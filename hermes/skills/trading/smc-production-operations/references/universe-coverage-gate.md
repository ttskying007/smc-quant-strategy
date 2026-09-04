# Market-Universe Coverage Gate

## Core distinction

`N/N passed` proves only the integrity of the **cached set**. It does **not** prove full-market coverage unless the denominator comes from a dated, canonical master universe that is independent of the cache.

Never describe a source-local cache audit as "full market" merely because every cached symbol passed.

## Required coverage ledger

Before full-market SMC research, write a dated ledger by asset class:

| Asset class | Canonical count | Complete multi-timeframe cache | Missing | Coverage | Decision |
|---|---:|---:|---:|---:|---|
| SH/SZ equities | | | | | |
| BJ equities | | | | | |
| ETFs | | | | | |
| Broad indices | | | | | |
| Industry/sector/board indices | | | | | |

The canonical source must be independently enumerated and timestamped. A local cache directory is not a canonical universe. If a live provider is used only as a probe and cannot enumerate an asset class (for example BJ), declare it a lower bound rather than a final denominator.

## Gates

- **Partial same-source diagnostics:** allowed only when the cached subset has passed provenance, chronological, 15m-slot, 60m-slot, and same-source aggregation audits. Label all outputs `CACHED_SUBSET`.
- **Full-market research:** blocked unless every required asset class has a canonical count and 100% complete same-source data for the declared scope.
- **Production / promotion:** blocked unless full-market research passes; never promote a strategy based on a partial cached subset.
- **Cross-provider comparisons:** evidence only. Never fill missing symbols or bars from an alternate provider.

## Failure reporting

Report the exact denominator, numerator, missing count, asset classes excluded, and whether the blocker is a master-universe gap, data-source gap, or cache-build gap. Do not conceal excluded BJ stocks, ETFs, indices, or boards inside a generic "stock universe" number.

## Example correction pattern

If 2,861 cached symbols pass all internal checks while the legacy local stock list contains 4,904 codes, the valid result is:

```text
CACHED_SUBSET_INTEGRITY_PASS
coverage = 2,861 / 4,904 = 58.34%
FULL_MARKET_RESEARCH_BLOCKED
```

—not `full-market cache complete`.
