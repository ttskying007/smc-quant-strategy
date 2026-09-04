# V320-V321 Fresh Supply and V246 Readiness Closure

Session date: 2026-07-09

Use when continuing after V316-V319 closure and considering whether to replace V185 or keep researching.

## V320 fresh raw-Kline supply vs V185

Artifact: `/root/.hermes/smc_audit/v320_fresh_supply_vs_v185_latest.json`
Script: `/root/.hermes/scripts/v25/v320_fresh_supply_vs_v185_audit.py`

Purpose: test a genuinely different daily raw-Kline supply source (`V262 fresh BOS -> demand retest`) combined with current V185 baseline, instead of filtering V185/V167 rows.

Result:

| Item | Value |
|---|---:|
| V185 baseline | n=334 / net WR=85.6287 / avg=6.5628 / year min=81.25 |
| fresh non-overlap candidates | 26,398 |
| fresh raw WR / avg | 41.3857% / +0.0831% |
| atoms | 140 |
| rules tested | 606 |
| production pass | 0 |
| best combined rule | `raw_prev20_range_pct>=29.0871 AND raw_prev10_range_pct<=8.0679` |
| best combined metrics | n=370 / WR=81.6216 / avg=6.0157 / year min=80.137 |

Conclusion: V262 fresh raw daily supply is too noisy. Combining it with V185 degrades both WR and avg. Do not route or continue simple scalar pruning on this source.

## V321 V246/V248 vs V185 promotion readiness

Artifact: `/root/.hermes/smc_audit/v321_v246_vs_v185_promotion_readiness_latest.json`
Script: `/root/.hermes/scripts/v25/v321_v246_vs_v185_promotion_readiness_audit.py`

Purpose: V248/V246 historical candidate is much stronger than V185, but prior decision required current scanner smoke. V321 consolidates historical pass + current scanner reconstruction.

Historical V248/V246 selected metrics:

| Metric | Value |
|---|---:|
| n | 573 |
| WR | 94.4154% |
| avg | +7.6022% |
| min_year_n | 71 |
| year WR min | 92.22% |
| micro_profit_pct | 0.349% |
| T+1 | 0 |
| selector leak fields | 0 |

Current V246 scanner reconstruction after rerunning V164 + V246 daily current audit:

| Metric | Value |
|---|---:|
| latest market date | 20260708 |
| dry recent45 rows | 1457 |
| parent raw rule rows | 0 |
| raw rule rows | 0 |
| new actionable rows | 0 |
| selector leak fields | 0 |
| active outcome pollution | 0 |
| time order bad | 0 |

Decision: `V321_HISTORICAL_PASS_BUT_CURRENT_SCANNER_NOT_ACTIONABLE__KEEP_V185`

Reason: V248/V246 dominates V185 historically, but its current scanner branch has zero actionable rows. Do not switch production routing unless the user explicitly wants a historical-only backtest view; for live production baseline, keep V185.

## Important nuance

Rerunning V164 on current V90 scanner produced 131 recent45 corrected BUY rows and 2 latest-date rows, but the stricter V246 parent/current rule still emitted 0 raw/actionable rows. This means the blocker is not a stale V164 file; the V246 current parent selector itself is currently empty.

## Closed branches after V321

- V185 row scalar filters (V315)
- V185 exit matrix (V316)
- V185 dynamic exit overlay (V317)
- V167 broad candidate filtering (V318)
- current local 60min full-history promotion (V319)
- V262 fresh daily BOS/demand retest supply (V320)
- V248/V246 production replacement right now (V321: historical pass but current actionable=0)

## Current operational conclusion

Keep V185 as production/live baseline. Keep V248/V246 as a historically superior shadow candidate that is not live-actionable today. Next meaningful work is not another scalar filter; it must either:

1. build a current scanner-compatible version of the V248/V246 parent rule that actually emits rows without leak, or
2. build a new raw-Kline generator with a stronger semantic event than V262, then validate against the fixed gate.
