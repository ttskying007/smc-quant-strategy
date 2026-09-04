# V178/V179 TIME exit boundary (2026-06-24)

When V177 generic BE/trailing/partial-profit grids fail on V175, continue with attribution, not another global exit grid.

## V178 daily TIME-row attribution

Source: `/root/.hermes/smc_opt_v175_semantic_split/v175_trades.json`.
Artifact example: `/root/.hermes/smc_audit/v178_v175_time_path_attribution_20260624_203220/`.

Findings on V175 TIME exits:

- 65 TIME rows total.
- `MID_MFE_0P5_1P2R_GIVEBACK`: 27 rows, WR 62.96%, Avg +0.6385%, avg maxR 0.8395, avg givebackR 0.7793.
- `NEAR_TP_OR_LARGE_GIVEBACK`: 10 rows, WR 50.00%, Avg +1.3156%, avg maxR 1.3707, avg givebackR 1.2807.
- `TIME_WINNER_HELD_OK`: 9 rows, WR 100%, Avg +6.5659%; do not apply blanket early-exit rules to these winners.
- `NO_FOLLOW_THROUGH_LT_0P5R`: 8 rows; exit-layer rules cannot create edge if price never develops.

Decision: attribution-only, no production/frontend/watchlist writes.

## V179 60min feasibility probe

Artifact example: `/root/.hermes/smc_audit/v179_v175_time_60min_probe_20260624_203649/`.

Tencent 60min endpoint can refresh recent 500 bars but does not cover historical 2023-2025 TIME rows. In the probe:

- 65/65 symbols fetched successfully.
- Only 9/65 TIME rows had entry→exit 60min coverage (13.85%), all from 2026.
- Covered 2026 rows: 4 held reasonably, 3 mid-MFE giveback, 1 near-TP giveback, 1 intraday TP reachable.

Decision: 60min coverage insufficient for production/research gate. Do not claim production improvement from the 9-row covered subset.

## Next correct path

- Do not run another generic exit grid on the whole V175 universe.
- If intraday execution is pursued, first obtain historical intraday data for 2023-2025, then test only `MID_MFE_0P5_1P2R_GIVEBACK` and `NEAR_TP_OR_LARGE_GIVEBACK` rows.
- Keep `TIME_WINNER_HELD_OK` untouched; early exits here cut winners and reproduce the V177 failure mode.
- Any candidate must still pass full V175 gate: n>=200, min_year_n>=35, WR>=84, AvgPnL>=6.2, all_year_WR>=82, micro<=1%, T+1=0, AvgPnL not below V175.
