# V286 rolling period stock-DNA audit

## Trigger

Use when Lei asks whether stock DNA should adapt by time segment because a stock's controlling capital/operator may only manipulate a stock for a limited period and may change over time.

## Question

Can a rolling, time-segment-specific stock DNA selector solve the V280/V285 failure?

Hypothesis tested:

`recent 90/180/360-day stock-specific best SMC chronological grammar -> next-month candidate selection`

This is stricter than in-sample DNA and stricter than year-level walk-forward: every next-month decision only uses events before that month.

## Artifacts

- Script: `/root/.hermes/scripts/v25/v286_rolling_period_stock_dna_audit.py`
- Latest summary: `/root/.hermes/smc_audit/v286_rolling_period_stock_dna_latest.json`
- Selected rows: `artifacts.selected_rows` in the summary JSON

## Current V280 combination scheme audited

1. `REV_SSL_CHOCH_OB`: SSL sweep -> confirmed swing-high break/displacement -> true bearish candle OB -> touch+reclaim -> next-day entry
2. `UP_CONT_BOS_OB`: confirmed swing-high BOS/displacement -> true bearish candle OB -> touch+reclaim -> next-day entry
3. `ABSORB_SSL_FAST_MSS`: SSL sweep -> local 5-bar MSS -> last bearish candle POI -> next-day entry
4. `RANGE_LOW_SWEEP_RECLAIM`: RANGE regime -> range-low SSL sweep/reclaim -> same-bar POI -> next-day entry

## What is already adaptive

- V279/V280 adapt `liq_win` and `wait` from each stock's pre-event `swing_gap`.
- V285/V286 select bucketed dimensions such as `liq_age`, `reaction_delay`, `range60`, `risk`, `vol_ratio`, and family/regime combinations.

## What is not adaptive enough

- Continuous per-stock interval parameters are not learned directly; only bucketed selector dimensions are used.
- Multi-timeframe status is not solved: V283/V284 used 60m as overlay on daily zones; they did not generate same-source lower-timeframe POI first.
- Existing DNA is mostly historical rule performance + simple pre-entry buckets. It does not explicitly model operator lifecycle: accumulation/manipulation/distribution, active POI family, rhythm shift, and same-source 60m takeover POI.

## V286 results

Raw V280 test period 2024-2026:

- n=70,556
- WR=47.33%
- Avg=+0.68%
- 2026 WR=40.17%
- min monthly WR=21.74%

Rolling stock-DNA selectors:

| Selector | N | WR | Avg | 2024 | 2025 | 2026 | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| 90d stock DNA | 3,064 | 46.61 | +0.60 | 45.58 | 50.15 | 39.76 | fails; too reactive/noisy |
| 180d stock DNA | 4,063 | 48.29 | +0.78 | 48.02 | 50.76 | 41.43 | weak improvement, not enough |
| 360d stock DNA | 4,441 | 49.40 | +0.86 | 50.27 | 51.44 | 43.01 | best stock-DNA, still far below production |
| 180d pnl DNA | 4,252 | 47.98 | +0.72 | 48.06 | 50.30 | 40.90 | fails |

Rolling global-rule selectors:

| Selector | N | WR | Avg | 2024 | 2025 | 2026 | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| 180d global | 573 | 54.10 | +1.50 | 55.47 | 55.43 | 47.37 | quality improves but too sparse/unstable |
| 360d global | 488 | 56.56 | +1.83 | 66.33 | 56.99 | 47.46 | quality improves but too sparse/unstable |

## Conclusion

Rolling period DNA confirms Lei's hypothesis directionally: stock behavior is period-dependent, and long-window recent DNA is better than fixed annual/in-sample DNA. But it does not solve production quality.

The reason: current DNA is selecting among imperfect daily grammar families. It can choose which imperfect pattern recently worked, but it cannot identify whether an operator is currently in accumulation, manipulation, distribution, or whether daily POI and lower-timeframe takeover POI are same-source.

## Next architecture

Do not continue widening fixed windows or using historical WR white-lists.

Required architecture:

`Market/Industry Regime -> Stock Operator Lifecycle State -> SMC Story Family -> Adaptive Interval/Rhythm -> Same-source 60m POI/Takeover -> Daily executable contract`

The next generator should build the lower-timeframe takeover POI first, then map it back to daily regime/POI. Do not keep using daily zone and then ask 60m to confirm it after the fact.
