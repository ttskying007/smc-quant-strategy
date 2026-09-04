# V164→V167 scanner-contract to production-candidate gate

Use this when a scanner-time dry-run rule passes field integrity but still needs economic and endpoint isolation proof before production routing.

## Fixed acceptance boundary

Production-usable requires all of:

- `n >= 200`
- yearly robustness window `entry_year >= 2023`
- `min_year_n >= 35`
- `WR >= 82%`
- `avg_pnl >= 3%`
- `micro_profit_pct <= 1%`
- `T+1 violations = 0`
- `synthetic BE rows = 0`
- scanner-time dry-run fields complete for BUY rows
- outcome-leak BUY rows = 0
- no frontend/watchlist/production writes until endpoint/browser smoke passes

Research-usable but not promotable:

- `n >= 80`, `min_year_n >= 15`, `WR >= 72%`, `avg_pnl >= 1.5%`, `T+1=0`.

Anything below that is unusable.

## V165 lesson

V164 TRUE_TAKEOVER scanner rule as a whole is not production-usable even with high WR:

- Best whole-rule variant: `R0.5_H60_SLBUF0.0`
- `n=11009`, `WR=91.32%`, `avg=1.2048%`, `micro=2.54%`
- Fails production because avg < 3%, micro > 1%, and stale 2017 rows pollute full-window yearly minimum.

Conclusion: do not promote broad TRUE_TAKEOVER reclaim gates just because WR is high.

## V166 production candidate found

Search scanner-time-only slices across TP/SL/hold variants. Best production-usable slice:

```text
Rule fields:
market_state == BEAR_RISK
poi_source == DEMAND_OB
v132_reclaim_class == TRUE_TAKEOVER_3_STRICT
v132_reclaim_bull_body_pct <= 65

Execution contract:
TP = 1.5R
max_hold = 10 bars
SL = zone_low - 1.0% buffer
T+1 exit starts at entry_idx + 1
```

Historical robustness over entry_year>=2023:

- `n=793`
- `WR=82.09%`
- `avg=4.5403%`
- `micro=0.63%`
- yearly counts: 2023=158, 2024=289, 2025=266, 2026=80
- yearly WR: 2023=80.38%, 2024=80.62%, 2025=83.83%, 2026=85.00%
- `T+1=0`

Artifacts:

- `/root/.hermes/smc_audit/v166_v164_slice_variant_search_20260623/summary.json`
- `/root/.hermes/smc_audit/v166_v164_slice_variant_search_20260623/v166_production_slices.csv`
- `/root/.hermes/smc_audit/v166_v164_slice_variant_search_20260623/v166_best_production_slice_rows.csv`

## V167 exact scanner dry-run lesson

Implement the exact V166 rule as a read-only scanner dry-run before any frontend write.

Verified V167 dry-run:

- `source_rows=38976`
- `buy_rows=793`
- `recent45_buy_rows=33`
- latest BUY date `20260617`, latest BUY rows `1`
- BUY required fields complete = true
- missing source body rows = 12, but all safely routed WATCH_ONLY
- outcome-leak BUY rows = 0
- decision-unavailable BUY rows = 0
- base V164 fail BUY rows = 0
- V166 count match = true

Artifact:

- `/root/.hermes/smc_audit/v167_exact_scanner_dry_run_20260623/summary.json`

## V168 endpoint isolation lesson

After V167 passes, still do not promote until verifying current frontend/API is isolated.

Verified V168:

- Current `/api/summary`: V102, not V167/V152
- Current `/api/picks`: 33 rows, no V167 engine
- Current `/api/live-prices`: total 5, tradableLiveCount 0, watchContextCount 5
- `smc_unified.py` has no V167 route
- root + picks browser smoke loaded, console/js errors = 0
- no production/frontend/watchlist write was made

Artifact:

- `/root/.hermes/smc_audit/v168_v167_pre_promotion_endpoint_isolation_20260623/summary.json`

## V169 promotion closure

V167 was promoted through an isolated V169 artifact bundle, not by overwriting old V88/V102 files.

Artifacts:

- Builder: `/root/.hermes/scripts/v25/v169_apply_v167_production_candidate.py`
- Output dir: `/root/.hermes/smc_opt_v167_exact_scanner_gate/`
- Trades: `v167_trades.json` = 793 historical contract rows from V166, `entry_year>=2023`
- Active picks: `v167_active_picks.json` = 33 recent45 V167 scanner dry-run BUY rows, explicitly `pick_scope=ACTIVE_CANDIDATE`, `exit_date=''`
- Report: `/root/.hermes/smc_audit/v169_v167_production_promotion_20260623/report.md`

Promotion routing in `smc_unified.py`:

- Keep `ACTIVE_VERSION=V88` as the legacy route shell.
- Add `V167_DIR` and make `_promoted_contract_dir()`, `_promoted_trade_file()`, `reload_metrics()`, `_merge_v90_daily_picks()`, and `_merge_v91_shadow_picks()` prefer V167 artifacts when present.
- Include `production_eligible_v167` in `_v100_production_rows()` or the V167 trade cache filters to zero rows.
- For V167 active picks, do **not** pass through `_latest_v88_scanner_rows()` because it re-slices by latest V90 month and silently drops valid recent45 rows. Return the deduped V167 active file directly.
- K-line version dropdown is still value `V88` for compatibility but visible label must use `{FRONTEND_VERSION} 生产合同`, otherwise the page says V167 while the dropdown says V102.

Verified smoke after restart:

- `/api/reload`: trades=793, picks=33
- `/api/summary`: version=V167, engine=V167_EXACT_SCANNER_GATE, total=793, WR=82.1, avg=4.54, active_pick_count=33
- `/api/picks`: 33 rows, engine=V167_EXACT_SCANNER_GATE, scope=ACTIVE_CANDIDATE, exit_date rows=0
- `/api/live-prices`: total=33, tradableLiveCount=33, watchContextCount=0, dataDate=20260622
- `/api/kline_full?symbol=688327.SH&tf=daily`: trade_count=1, highlight=true
- Browser: dashboard title `SMC V167 Dashboard`; K-line dropdown `V167 生产合同`; console JS errors=0

## V170/V171 live degradation and frontend-contract closure

Do not treat scanner-time `ACTIVE_CANDIDATE` rows as automatically buyable at the current screen time. After promotion, run a live guard against the latest cached/live price:

- current price must be within `±1.5%` of `entry_price`
- current price must not already be `<= SL`
- current price must not already be `>= TP1`
- rows failing those checks remain visible as `WATCH_ONLY_CONTEXT`, not BUY

V171 repaired the V167 frontend field contract and live guard artifacts:

- Script: `/root/.hermes/scripts/v25/v171_v167_frontend_contract_live_guard.py`
- Report: `/root/.hermes/smc_opt_v167_exact_scanner_gate/v167_frontend_contract_live_guard_report.md`
- Required fields audited zero-missing for trades and active rows: `signal_price`, DNA, combo contract, weekly/daily/60min states, zone, cost line, volatility, dates.
- Historical V167 remains: `793` trades, `WR=82.09%`, `avg_pnl=4.5403%`, `T+1=0`.
- Static scanner/live-guard artifact at generation time: `33` recent rows -> `4 BUY_VALID / 29 WATCH_ONLY`.
- `/api/live-prices` re-evaluates current price dynamically, so `tradableLiveCount` can move intra-day as Tencent quotes change; always use `/api/live-prices` for the final real-time BUY count, and use `/api/summary` for historical production metrics/static artifact counts.

Verified endpoint/browser closure:

- `/api/reload`: trades=793, picks=33
- `/api/summary`: version=V167, engine=V167_EXACT_SCANNER_GATE, total=793, WR=82.1, avg=4.54
- `/api/picks`: 33 rows, 0 missing required frontend contract fields
- `/api/live-prices`: 33 rows, BUY rows are only the current-price-valid subset; WATCH_ONLY rows remain visible for context
- Pages `/`, `/monitor`, `/live`, `/backtest`, `/analysis`, `/autopsy`, `/docs`: V167 visible, no `DNA: UNKNOWN`, no missing-field banner
- Browser console on `/live`: JS errors=0

## Ongoing research direction after promotion

V167 is production-usable only under the fixed contract: `BEAR_RISK + DEMAND_OB + TRUE_TAKEOVER_3_STRICT + bull_body<=65 + TP1.5R/H10/SL zone_low-1% + T+1`.

Next research should focus on reducing live degradation before entry: compare WATCH_ONLY causes (`TP_ALREADY_HIT`, `SL_ALREADY_HIT`, `PRICE_NOT_NEAR_ENTRY`) by entry_date, risk_pct, entry_chase, bull_body_pct, and stale-age. If degradation clusters in stale rows or high-risk buckets, add an ex-ante scanner-time staleness/risk guard before changing TP/SL.
