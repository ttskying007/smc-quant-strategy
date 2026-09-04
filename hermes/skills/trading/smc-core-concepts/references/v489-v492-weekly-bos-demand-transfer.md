# V489–V492 Weekly BOS → Demand OB → Daily Transfer

Use when evaluating a genuinely higher-timeframe continuation ontology after local daily branches through V488 are closed.

## Frozen semantic contract

1. Aggregate local daily bars into completed ISO weeks; exclude the rightmost partial week.
2. Confirm a unique weekly 2-left/2-right swing high, visible only at pivot+2 weeks.
3. Require a later weekly close at least 0.3% above that confirmed high (weekly bullish BOS).
4. Scan backward at most 6 completed weeks for the nearest bearish weekly candle; use `[low, max(open, close)]` as weekly demand OB.
5. Reject if any week between OB and BOS already wicks into the OB.
6. Only after the completed BOS week: daily wick touch → later close reclaim above zone → later hold above zone → next-session open eligibility.
7. No outcomes are read during generation.

## Verified results

- Full universe: 4,897 symbols.
- Semantic seeds: 58,569; every 2023–2026 year exceeds support floor.
- Independent raw-bar oracle: 58,569/58,569 pass, zero chronology mismatch, no outcome headers.
- Frozen execution: next open; SL=weekly zone low×0.99; nearest confirmed weekly swing high visible by hold as TP; time30; 0.2% cost; strict T+1; one replay.
- Closed trades: 57,038.
- Aggregate: gross WR 66.8905%, net≥0.8 WR 56.2905%, AvgNet +0.3769%, payoff 0.5925, PF 1.1233, SL 27.8130%.
- 2023: n=1,797, WR 44.4073%, AvgNet -2.1936%, PF 0.5447.
- 2024: n=12,924, WR 59.3315%, AvgNet -0.5465%, PF 0.8728.
- 2025: n=32,126, WR 71.7923%, AvgNet +1.0042%, PF 1.4294.
- 2026: n=10,191, WR 64.9887%, AvgNet +0.0237%, PF 1.0069.
- T+1 violations=0; duplicate symbol-entry=0; independent metric audit exactly matches report.

## Decision

Close this ontology. Aggregate WR is misleading: average loss (-8.8511%) dominates average win (+5.2439%), 2023/2024 expectancy is negative, and the result is heavily 2025-dependent. Do not reopen through weekly BOS threshold, OB lookback, retest wait, SL, target, or hold tuning.

Artifacts: `v489_weekly_bos_demand_transfer_latest.json`, `v490_weekly_bos_demand_transfer_oracle_latest.json`, `v491_weekly_bos_demand_transfer_frozen_t1_replay_latest.json`, `v492_weekly_bos_demand_independent_metric_audit_latest.json`.
