# Frozen SMC economic-closure pattern

## Purpose

Use this pattern when a new causal SMC ontology has enough full-universe support and passes a raw-bar semantic audit, but must still prove its economics under a single pre-registered execution contract. It prevents turning a correctly detected signal into a false production strategy through post-outcome filtering.

## Required chain

1. **Outcome-blind seed** — read only declared source OHLCV/PIT fields. Persist causal identities and eligible date, not PnL, exits, stops, targets, historical trade files, or current watchlists.
2. **Independent semantic audit** — recompute every seed from raw bars. Audit pivot confirmation, first crossing, OB origin/pricing, full lifecycle ordering, and entry after signal.
3. **Frozen execution preregistration** — before opening outcomes, fix next-open entry, structure stop, pre-entry unconsumed target with planned RR floor, strict T+1 exit start, conservative same-bar collision handling, fee, time stop, and serial-position rule.
4. **One replay only** — emit trade CSV and calculate outcomes exactly once. No selectors or parameters are explored after results appear.
5. **Independent metric audit** — recalculate all metrics directly from the CSV and check chronology (`signal < confirmation < entry < exit`), planned RR, exit reason counts, and all user gates.
6. **Close or promote** — promote only if all gates pass. On any frozen failure, preserve research artifacts and make production a no-write EMPTY_BOOK.

## Full-universe daily reference outcome

The following canonical ontology was tested using local full-universe daily OHLCV:

`confirmed 3L/3R BOS → backward nearest bearish demand OB → touch without close invalidation → reclaim → hold → next-session open`

### Semantic stage

- Outcome-blind seeds: **49,256**
- Symbols: **4,887**
- Annual support: 2023 **6,594**; 2024 **13,374**; 2025 **20,372**; 2026 partial **8,916**
- Independent raw semantic audit: **49,256 / 49,256 passed**

The semantic audit confirms the detector can be causal and structurally correctly anchored. It does not assert profitability.

### Frozen execution

- Entry: open following the hold confirmation
- Stop: demand OB low × 0.99
- Target: nearest unconsumed, right-confirmed pre-entry swing high with planned RR ≥1.5
- Exit starts: entry session +1 only (strict A-share T+1)
- Collision: stop first; gap-aware open handling
- Time stop: 20 sessions
- Fee: 0.20% round trip
- Position policy: one serial position per symbol

### Independent result

- Trades: **27,490**
- Strict chronology/T+1 violations: **0**
- Planned RR below 1.5: **0**
- Overall: WR **37.9556%**, average net **+0.5004%**, PF **1.1389**, payoff **1.8617**
- 2023: n **3,361**, average net **−1.43%**
- 2024: n **9,850**, average net **+0.0278%**
- 2025: n **14,279**, average net **+1.2809%**

For a gate of total n≥1,000; yearly n≥300; WR≥55%; average net≥+0.50%; PF≥1.15; payoff≥0.70; every year positive; T+1=0, this ontology fails **WR**, **PF**, and **every-year positive expectancy**.

## Decision discipline

Do not call this a data error, a future-leak result, or a reason to alter parameters: semantic and T+1 invariants passed. The rejection is economic and cross-year. Close this exact ontology and prohibit post-hoc changes to filters, entry timing, stops, targets, holding period, year slice, symbol subset, or thresholds.

Research may reopen only with a genuinely independent, date-addressable PIT dimension or a new complete canonical intraday data source, followed again by the same outcome-blind → semantic-audit → frozen-replay → independent-metric-audit chain.
