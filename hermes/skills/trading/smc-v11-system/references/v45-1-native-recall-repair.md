# V45.1 Native Recall Repair + Frontend Validation Lessons

Session context: V45 Native event-sourced engine passed correctness contracts but produced only 1 trade. User asked to execute the planned repair fully, verify, and sync frontend diagnostics.

## Durable lesson

When an SMC engine is "correct but too sparse", do **not** fall back to chase/direct-signal-close. Repair recall while preserving the event lifecycle contract:

```text
liquidity -> structure -> POI -> raw retest -> execution sub-zone -> confirmation -> armed/trade
```

The fix class is **legal setup lifecycle expansion**, not metric tuning.

## V45.1 pattern that worked

Add a new recall-repair engine/script rather than mutating the baseline until contracts are proven:

```text
/root/.hermes/scripts/v25/v45_1_recall_repair.py
```

Outputs should include both final trading artifacts and diagnosis artifacts:

```text
events_v45_1.json
setups_v45_1.json
v45_1_trades.json
v45_1_picks.json
v45_1_watchlist.json
v45_1_replay_audit.json
v45_1_full.json
v45_1_report.json
v45_1_validation_summary.json
```

## Correctness contract to preserve

A valid V45-style native repair must explicitly validate:

```text
native_from_kline_not_v44_trade_reconstruction = true
full_market_files > 4000
entry_gate_coverage = 1.0
entry_inside_raw_zone_coverage = 1.0
entry_inside_execution_zone_coverage = 1.0
direct_signal_close_trade_count = 0
standalone_ifvg_trade_count = 0
expired_setup_traded_count = 0
invalidated_setup_traded_count = 0
active_picks_not_historical_all_market = true
correctness_contract_passed = true
```

If these checks fail, do not report production success even if WR/RR improves.

## Recall repair mechanisms allowed

Allowed expansions:

1. Add continuation branch **only if** it still has full lifecycle events and POI retest.
2. Add `execution_zone` / execution sub-zone inside raw zone.
3. Add confirmation types that happen after execution-zone retest:
   - `BULLISH_REJECTION_EXEC_MID_RECLAIM`
   - `PINBAR_EXEC_MID_RECLAIM`
   - `TWO_BAR_REJECTION_HOLD`
   - `DISPLACEMENT_AFTER_EXEC_RETEST`
4. Generate active picks from setup lifecycle state, not from completed historical trades.
5. Generate watchlist states:
   - `WAITING_FOR_RETEST`
   - `RETESTED_WAITING_CONFIRM`
   - `ARMED_READY`

Forbidden regressions:

```text
DIRECT_SIGNAL_CLOSE
chase fallback
standalone IFVG
trading display zone instead of raw/execution zone
completed-trade-derived active picks
```

## Frontend/API sync checklist

When adding a V45.x diagnostic engine, expose it in `smc_unified.py` with dedicated diagnostic routes instead of replacing the main production dashboard prematurely:

```text
/v45
/api/v45/report
/api/v45/validation
/api/v45/events
/api/v45/setups
/api/v45/trades
/api/v45/picks
/api/v45/watchlist
```

Keep `/stoploss` for V44/V-current stop-loss attribution when diagnosing whether losses came from signal definition, entry timing, combination method, or unfilled entry level.

## Large JSON frontend pitfall

`/api/summary` must not materialize a 200MB+ full-trade JSON just for health/summary. Use a fast summary path or precomputed metrics and lazy-load detailed trades only on detailed pages. Otherwise restarting the Python HTTP frontend can OOM/exit while handling the first health request.

Fast summary path should avoid helpers that call `get_picks_cached()` or `get_default_trades()` if they load large files.

## Verification sequence

After implementation:

1. `python3 -m py_compile smc_unified.py v45_1_recall_repair.py`
2. Run full-market V45.1 engine.
3. Read `v45_1_validation_summary.json` and verify correctness + recall contracts.
4. Restart frontend on 8890.
5. Probe:

```text
/api/summary
/stoploss
/v45
/api/v45/validation
/api/v45/picks
/api/v45/watchlist
```

6. Confirm process remains alive and RSS is reasonable after `/api/summary`.

## Reporting style for Lei

Report compactly as completed work + exact metrics + file paths + verified endpoints. Avoid process narration or choices. State whether the result is production-ready, diagnostic-only, or candidate-for-review based on the validation contract, not on a single WR/RR figure.
