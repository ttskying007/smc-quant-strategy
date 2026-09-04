# V325–V327 V246 promotion/current-supply closure

Date: 2026-07-09

## Trigger
Use when a historically strong SMC candidate (especially V246/V248) passes backtest metrics but current scanner/active candidates are missing or stale.

## Historical result is real but not sufficient
V246/V248 historical selected set passed the production-width gate:
- `n=573`, WR `94.42%`, AvgPnL `7.60%`
- year counts `2023=90, 2024=202, 2025=210, 2026=71`
- min yearly WR `92.22%`
- micro-profit `0.349%`, T+1 violations `0`

Do **not** promote from this alone. It is a historical selected row set, not proof of current executable supply.

## V325 root cause
The existing `v246_daily_current_shadow_audit.py` strict parent rule reconstructed only `21/573` historical V246 rows (`3.66%`). It is a stale single-parent route, not the real V246 lineage generator.

V246 historical rows actually came from multiple lineages:
- `V161_DRY_RUN_SCANNER_CONTRACT`: 174 rows
- `V175_BASELINE`: 164 rows
- `V211_CHILD`: 160 rows
- `V185_CHILD`: 75 rows

The reproducible `v164_rule_pass` subset alone had `n=498`, WR `94.18%`, Avg `7.42%`, minYear `68` — below V246 production gate (`n>=570`, minYear>=70, Avg>=7.6).

## Required current-supply audit pattern
Before routing any historical candidate to production/API/frontend:
1. Rerun latest scanner source (`v90_daily_full_market_scanner.py` if needed), then rerun V161/V164 dry-run contracts.
2. Rebuild each historical lineage separately on current scanner rows:
   - V161/V164 + V246 weak-industry addback.
   - V175/V172 gate: `DEMAND_OB`, `BEAR_RISK`, `true_takeover_3_strict`, `v85_zone_width_pct>=2`, `post_pullback_depth3<=2`, plus V246 industry addback.
   - V211 child: `true_takeover_2`, not strict3, `bull_count3>=3`, `post_pullback_depth3<=3`, plus V246 industry addback.
3. Deduplicate source-side only: lower `risk_pct`, then lower `entry_chase_above_zone_pct`; never use outcome fields.
4. Exclude history overlap (`symbol+entry_date`) with V185/V231/V236/V246 historical rows and active rows.
5. Require current executable candidates: `actual_bars_since_entry <= 10` under latest local K-line cache, not stale `bars_since_entry` fields.
6. Replay every surviving candidate with executable T+1 contract before endpoint routing:
   - `SL = zone_low * 0.99`
   - `TP = entry + 1.5R`
   - max hold `10` bars
   - T+1 only; if same daily bar touches both, count SL first.
7. Only rows still `OPEN_UNEXPIRED` after replay can proceed to endpoint mapping smoke. Rows already TP/SL/TIME are not active picks.

## V326/V327 latest closure
After rerunning V161/V164 from the latest V90 snapshot (`latest_market_date=20260708`):
- V164 corrected recent45 BUY rows: `131`.
- V246 lineage current supply found one non-history <=10-bar candidate: `688689.SH / 20260610`, appearing in V161 and V175 routes.
- V327 executable replay closed it on T+1: TP hit on `20260611`, entry `38.792`, TP `42.5518`, PnL `+9.6922%`, same-day violation `false`.
- Open executable current V246 rows: `0`.

Decision: `V327_NO_OPEN_EXECUTABLE_CURRENT_V246_ROWS__NO_ENDPOINT_ROUTE__NO_WRITE`.

## Operational rule
Keep V185 production unchanged. Keep V246/V175/V211 as historical/shadow research until a future scanner run yields non-history, <=10-bar, replay-open rows. Do not route V246 to `/api/picks`, watchlist, frontend default, or morning push when executable replay returns zero open rows.

## Artifacts
- V325: `/root/.hermes/smc_audit/v325_v246_route_promotion_blocker_latest.json`
- V326: `/root/.hermes/smc_audit/v326_v246_lineage_current_supply_latest.json`
- V327: `/root/.hermes/smc_audit/v327_v326_current_candidate_executable_replay_latest.json`
- Scripts:
  - `/root/.hermes/scripts/v25/v325_v246_route_promotion_blocker_audit.py`
  - `/root/.hermes/scripts/v25/v326_v246_lineage_current_supply_audit.py`
  - `/root/.hermes/scripts/v25/v327_v326_current_candidate_executable_replay.py`
