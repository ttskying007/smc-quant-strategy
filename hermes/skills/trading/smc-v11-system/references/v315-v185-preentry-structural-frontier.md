# V315 V185 pre-entry structural frontier audit

Date: 2026-07-07

## Trigger

Use when continuing after V185 production and V100 economic autopsy rejection, especially when the user asks to keep researching without repeating old scalar/exit branches.

## Goal

Test whether V185 can be improved by a **non-leaking pre-entry structural layer** derived only from:

- V185 scanner/source fields already known at entry time;
- local daily K-line geometry before the entry bar (`*_daily_750.json`);
- no outcome fields (`pnl`, `exit_reason`, `MFE/MAE`, hit flags, hold bars) and no production/frontend/watchlist writes.

Script:

```bash
python3 -m py_compile /root/.hermes/scripts/v25/v315_v185_preentry_structural_frontier_audit.py
python3 /root/.hermes/scripts/v25/v315_v185_preentry_structural_frontier_audit.py
```

Artifacts:

- Latest: `/root/.hermes/smc_audit/v315_v185_preentry_structural_frontier_latest.json`
- Rows/features: `.../v315_rows_with_preentry_features.json`

## Fixed gates

Production improvement over V185 requires:

| Gate | Threshold |
|---|---:|
| n | >=300 |
| min_year_n | >=40 |
| net WR (`pnl_pct>=0.8%`) | >=87% |
| AvgPnL | >=6.8% |
| all_year_WR_min | >=84% |
| micro_profit_pct | <=1% |
| T+1 violation | 0 |

Research usable requires at least `n>=260`, `min_year_n>=35`, net WR>=88%, Avg>=6.8%, year min>=84%, micro<=1%, T+1=0.

## Result

V315 tested 334 V185 rows, 334/334 K-line coverage, 49 safe features, 485 single rules, and 2,649 two-feature rules.

| Result | Count |
|---|---:|
| Production pass | 0 |
| Research pass | 0 |
| T+1 violations | 0 |

Decision:

`KEEP_V185_PRODUCTION__NO_V315_PREENTRY_STRUCTURAL_GATE_PASS`

## Important metric nuance

V185 historical summary reports gross WR around 86.23%. V315 also reports economic/net WR with `pnl_pct>=0.8%`:

| Metric | Value |
|---|---:|
| gross WR (`pnl>0`) | 86.23% |
| net WR (`pnl>=0.8`) | 85.63% |
| small wins `0<pnl<0.8` | 2 rows / 0.60% |
| AvgPnL | 6.5628% |

The 2 small wins are not large pollution, but V315 should still use net WR for production promotion after the V99/V100 lesson.

## Root-cause evidence

Losers still show the same pre-entry structural pattern: entry/reclaim too high in the recent range and less target room.

Top loser-vs-winner deltas:

| Feature | Winner mean | Loser mean | Delta |
|---|---:|---:|---:|
| pre_close_pos_60d_pct | 44.61 | 51.41 | +6.80 |
| pre_close_pos_3d_pct | 67.34 | 74.08 | +6.74 |
| pre_close_pos_10d_pct | 64.29 | 70.70 | +6.40 |
| v132_reclaim_close_pos_pct | 74.79 | 81.09 | +6.30 |
| target_room_prior60_high_pct | 22.72 | 17.71 | -5.01 |

Interpretation: weak rows are more chase-like / higher in local range / have less prior-high target room. This is a real mechanism signal, but gating it collapses sample/year coverage.

## Best non-promotable pockets

| Rule | n | Net WR | Avg | min_year_n | year min | Status |
|---|---:|---:|---:|---:|---:|---|
| `reclaim_close_pos<=0.8444 AND pre_ret_3d_pct>=-0.949367` | 187 | 91.98% | 7.406 | 14 | 86.49 | closed: sample/year collapse |
| `reclaim_close_pos<=0.8664 AND v85_zone_width_pct<=3.125` | 184 | 91.85% | 6.91 | 15 | 87.27 | closed: sample/year collapse |
| `reclaim_close_pos<=0.8444 AND pre_vol_ratio_3d>=0.708391` | 198 | 91.41% | 7.254 | 17 | 88.24 | closed: sample/year collapse |
| `reclaim_close_pos<=0.8444 AND target_room_prior20_high_pct>=3.189793` | 197 | 91.37% | 7.271 | 15 | 90.00 | closed: sample/year collapse |

## Closure

Closed for now:

- daily pre-entry range-position filters;
- prior-high target room filters;
- short-window return/volume overlays;
- pairwise non-leaking scalar gates on V185 rows.

The mechanism diagnosis is useful, but it cannot safely supersede V185 because every high-WR pocket is too small and year-concentrated.

## Next direction

Do not keep mining V185 row-level scalar features. A new attempt must change information content or supply:

1. scanner-time new candidate supply, not historical V185 filtering;
2. longer/higher-quality intraday or sector leadership data with current-source contract;
3. production/live hardening while V185 remains baseline.
