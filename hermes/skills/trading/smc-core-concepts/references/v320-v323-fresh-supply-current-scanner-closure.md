# V320-V323 Fresh Supply / Current Scanner Closure

Session date: 2026-07-09

Use when continuing after V316-V319 V185 closure and the user asks to keep researching new directions.

## Gate used

Production improvement gate remained:

| Gate | Threshold |
|---|---:|
| n | >=300 |
| min_year_n | >=40 |
| net WR (`pnl_pct>=0.8`) | >=87% |
| AvgPnL | >=6.8% |
| all_year_WR_min | >=84% |
| micro_profit_pct | <=1% |
| T+1 | 0 |

## V320 raw compression breakout retest generator

Artifact: `/root/.hermes/smc_audit/v320_fast_raw_compression_breakout_retest_latest.json`

- Scanned 4,655 daily files / 4,618 usable symbols.
- Tested 6 raw compression→breakout→retest parameter sets × 5 exits.
- Production pass: 0.
- Best WR was only ~45%, Avg ~0.23%-0.29% depending config.
- Non-overlap with V185 was ~100%, proving it was truly fresh but unusable.

Conclusion: raw compression breakout/retest is not a usable SMC supply layer.

## V321 raw SSL sweep reclaim generator

Artifact: `/root/.hermes/smc_audit/v321_fast_raw_ssl_sweep_reclaim_latest.json`

- Scanned 4,655 daily files / 4,618 usable symbols.
- Tested 6 raw SSL sweep→reclaim parameter sets × 4 exits.
- Production pass: 0.
- Best config: `L60_P0.8_D2_C0.65_RR1.2_H10`, n=25,518 / WR=47.90 / Avg=0.27.
- Non-overlap with V185 ~99.97% but unusable.

Conclusion: raw SSL sweep/reclaim without the true-takeover source layer is too noisy and closed.

## V321 V246 vs V185 promotion readiness

Artifact: `/root/.hermes/smc_audit/v321_v246_vs_v185_promotion_readiness_latest.json`

Historical V246/V248 dominates V185:

| Engine | n | WR | Avg | min_year_n | year min |
|---|---:|---:|---:|---:|---:|
| V185 | 334 | 86.23 | 6.56 | 41 | 82.81 |
| V246/V248 historical | 573 | 94.42 | 7.60 | 71 | 92.22 |

But current direct reconstruction produced 0 V246 actionable rows, so no production switch.

Decision: `V321_HISTORICAL_PASS_BUT_CURRENT_SCANNER_NOT_ACTIONABLE__KEEP_V185`.

## V322 current scanner contract recompute

Artifact: `/root/.hermes/smc_audit/v322_current_scanner_contract_recompute_latest.json`

Purpose: diagnose why V246 current scanner emitted 0 actionable rows.

Key findings:

| Contract | Rows | actual actionable <=10 | non-overlap actionable <=10 |
|---|---:|---:|---:|
| strict V246 parent | 110 historical/stale rows | 0 | 0 |
| strict after industry | 109 historical/stale rows | 0 | 0 |
| direct V164 + V246 industry addback | 10,593 total / 126 recent45 | 1 | 1 |

Diagnosis:

- Strict V246 current parent rule is too narrow and does not reconstruct the V244/V246 historical source mix.
- Direct V164+industry addback can find 1 current shadow row, but this direct route is not historically validated as the exact V246 production route.

Decision: `V322_CURRENT_ACTIONABLE_DIRECT_ROWS_FOUND__SHADOW_ENDPOINT_NEXT` only, not production.

## V323 direct current shadow materialization

Artifact: `/root/.hermes/smc_audit/v323_v322_direct_current_shadow_latest.json`

One shadow-only row was materialized:

| Symbol | Entry date | Rule status | Replay |
|---|---|---|---|
| 688689.SH | 20260610 | V164 true takeover + V246 industry addback | TP on 20260611, +9.6922%, T+1 valid |

It is marked `SHADOW_MONITOR_ONLY`, `promotion_eligible=false` because the direct current route is not the exact historically validated V246 route; V167 exact historical quality is below production gate.

## Closed / open conclusions

Closed:

1. Raw compression breakout/retest generator (V320).
2. Raw SSL sweep/reclaim generator (V321).
3. Direct V164+industry current row as production route (V322/V323) — shadow only.

Still open only if continued:

1. Reconstruct exact V244/V246 current source mix, especially the historical base branch from V231/V236, not just child/current V164 rows.
2. Or keep V185 production baseline and use V323 row only as shadow evidence.

Do not promote V246 production until current scanner can emit exact-route rows with no historical-only dependency.
