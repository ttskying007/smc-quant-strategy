# V45.1/V45.2 Recall Repair + Quality Filter Lessons

Session context: after V45 Native proved the correct event lifecycle but produced only 1 trade, the engine needed recall repair without reverting to V44's polluted direct-chase behavior.

## Durable principles

- Keep V45 Native as the correctness contract: native K-line event ledger, not V44 trade reconstruction.
- Never restore `DIRECT_SIGNAL_CLOSE`, standalone IFVG, or any entry that has not touched the raw POI / execution zone.
- Active picks must come from setup lifecycle state (`WAITING_FOR_RETEST`, `RETESTED_WAITING_CONFIRM`, `ARMED_READY`), not from completed historical trades.
- Separate raw structural zone from tradable execution sub-zone:
  - raw zone = structure/invalidation boundary
  - execution sub-zone = where entry is allowed
- A recall repair is valid only if all correctness counters remain zero:
  - `direct_signal_close_trade_count == 0`
  - `standalone_ifvg_trade_count == 0`
  - `expired_setup_traded_count == 0`
  - `invalidated_setup_traded_count == 0`
  - `entry_above_raw_high_invalid_count == 0`
  - `entry_above_execution_high_invalid_count == 0`
  - `entry_inside_raw_zone_coverage == 1.0`
  - `entry_inside_execution_zone_coverage == 1.0`

## V45.1 recall repair pattern

Implemented as `/root/.hermes/scripts/v25/v45_1_recall_repair.py` with output under `/root/.hermes/smc_opt_v45_1/`.

Core repairs:

1. Add an independent continuation branch:
   `Trend/BOS continuation -> POI -> execution-zone retest -> legal confirmation -> armed`.
2. Add execution sub-zone for wide POI; do not simply widen SL or allow chase.
3. Add legal confirmation types at the zone:
   - `BULLISH_REJECTION_EXEC_MID_RECLAIM`
   - `PINBAR_EXEC_MID_RECLAIM`
   - `TWO_BAR_REJECTION_HOLD`
   - `DISPLACEMENT_AFTER_EXEC_RETEST`
4. Generate watchlist from unfinished lifecycle states.

Observed V45.1 result:

```json
{
  "n_trades": 392,
  "wr": 69.9,
  "avg_pnl": 2.51,
  "sl_rate": 29.1,
  "active_pick_count": 43,
  "watchlist_count": 1097,
  "correctness_contract_passed": true,
  "recall_acceptance_passed": true
}
```

## V45.1 branch autopsy

Before changing anything, split by `sequence_kind`, `zone_type`, `conf_type`, `market_state`, `entry_mode`, and `execution_zone_mode`. Useful findings:

- `PINBAR_EXEC_MID_RECLAIM`: 14 trades, WR 42.9%, SL 57.1%, avg -0.79. Treat as weak confirmation.
- `LIMIT_RETOUCH_EXEC_HIGH`: 39 trades, WR 59.0%, SL 41.0%. Delayed limit retouch behaved like a failing second pullback.
- `REVERSAL + FVG + TWO_BAR_REJECTION_HOLD`: 61 trades, WR 55.7%, SL 44.3%. Weak in reversal context.
- `CONTINUATION + FVG + BULLISH_REJECTION`: 113 trades, WR 74.3%, SL 24.8%.
- `CONTINUATION + FVG + TWO_BAR_REJECTION_HOLD`: 112 trades, WR 70.5%, SL 29.5%, avg 3.49. Keep despite moderate SL because expectancy is strong.
- `REVERSAL + FVG + BULLISH_REJECTION`: 46 trades, WR 73.9%, SL 26.1%.

## V45.2 quality-filter pattern

Implemented as `/root/.hermes/scripts/v25/v45_2_quality_filter.py` with output under `/root/.hermes/smc_opt_v45_2/`.

Rules applied:

1. Remove `PINBAR_EXEC_MID_RECLAIM`.
2. Remove delayed `LIMIT_*` entry modes.
3. Remove `REVERSAL + FVG + TWO_BAR_REJECTION_HOLD`.
4. Keep continuation/FVG two-bar branch because V45.1 evidence showed positive expectancy.

Observed V45.2 result:

```json
{
  "n_trades": 286,
  "wr": 75.5,
  "avg_pnl": 3.14,
  "sl_rate": 23.8,
  "active_pick_count": 30,
  "watchlist_count": 702,
  "correctness_contract_passed": true,
  "recall_acceptance_passed": true,
  "quality_improved_vs_v45_1": true
}
```

Filtered counts:

```json
{
  "FILTER_REVERSAL_FVG_TWO_BAR_WEAK": 51,
  "FILTER_DELAYED_LIMIT_RETOUCH_SL_HEAVY": 41,
  "FILTER_PINBAR_EXEC_MID_RECLAIM_SL_HEAVY": 14
}
```

## Frontend sync pattern

`/root/.hermes/scripts/smc_unified.py` was extended with:

- `/stoploss` and `/api/stoploss/audit` for V44 stoploss attribution.
- `/v45` and `/api/v45/*` for V45 Native/V45.1/V45.2 diagnostics.
- `ver` query param support: `/v45?ver=v45_2`, `/api/v45/validation?ver=v45_1`, etc.
- Fast summary path for V44 so `/api/summary` does not materialize the 216MB V44 full JSON and trigger OOM.

When adding new V45 variants, update `load_v45_bundle()` and expose status in `/api/summary` without changing the V44 main dashboard unless the candidate is explicitly promoted.

## Required validation commands

After any V45.x change:

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py /root/.hermes/scripts/v25/<engine>.py
python3 /root/.hermes/scripts/v25/<engine>.py
curl -s http://127.0.0.1:8890/api/v45/validation | python3 -m json.tool
curl -s http://127.0.0.1:8890/api/v45/picks | python3 -m json.tool | head
curl -s http://127.0.0.1:8890/api/v45/watchlist?limit=3 | python3 -m json.tool
```

Acceptance is not WR alone. Require correctness contract + recall + branch-level improvement evidence.
