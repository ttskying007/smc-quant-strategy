# V27 Architecture (2026-05-19)

## Core: smc_core_v27.py

`/root/.hermes/scripts/v25/smc_core_v27.py` — 1133 lines, strict event-based SMC signals.

### Signal Detection Pipeline

```
detect_all_signals_v27(klines)
  ├─ confirmed_swings(klines, left=3, right=3, noise=0.3*ATR)
  ├─ structure_signals(klines, swings) → BOS/CHOCH/MSS (state machine)
  ├─ fvg_list(klines) → FVGs
  ├─ bpr_signals(fvgs) → opposing-FVG overlap only
  ├─ sweep_signals(klines, swings) → confirmed-swing pierce+reclaim
  ├─ ob_signals(klines, struct_events) → event-anchored backward scan
  ├─ ote_signals(klines, struct_events, swings) → impulse-bound OTE
  └─ po3_signals(klines, sweeps, struct_events) → accumulation→manipulation→distribution
```

### Trade Pipeline

```
build_bullish_setups(signal_data, klines)
  For each bullish structure event:
    1. Displacement check: body > 30% of range
    2. Find zone (OB > OTE > BPR)
    3. Check zone invalidation up to event
    4. Scan ev_idx+1 to ev_idx+30 for retrace:
       - Close must be within zone (zl*0.97 to zh*1.03)
       - Zone invalidation check during scan
    5. Find confirmation (PINBAR preferred, BULLISH_REJECTION fallback)
    6. Entry = conf_idx + 1 (T+1)
    7. Filters: close > MA20, ATR >= 1.5%, min SL 2%, RR >= 0.8
    8. SL: zone_low - 0.5*ATR, TP: next confirmed swing high (or ATR-based)

backtest_setups(setups, klines)
  For each setup:
    Scan entry_idx+1 forward for SL/TP hits (max 60 bars)
    Track exit_reason, pnl_pct, hold_bars

compute_metrics(trades)
  WR, avgP, avgWin, avgLoss, RR, exit/zone/conf distributions
```

## Full Scan: v27_full_scan.py

`/root/.hermes/scripts/v25/v27_full_scan.py` — iterates kline_cache/*_daily_*.json, runs detect→setup→backtest per stock, writes smc_opt_v27/.

## Adapter: v27_adapter.py

Ensures frontend-compatible field names (won, sl_pct, entry_type, etc.)

## Quality Filter Progression (2026-05-19 session)

| Filter | Before | After | WR improvement |
|--------|--------|-------|----------------|
| Future leak fix (OTE) | 67.2% | 54.7% | Honest baseline |
| PINBAR-only confirm | 54.7% | 50.5% | Fewer weak confirmations |
| ATR-based SL/TP | 50.5% | 50.5% | No WR change |
| Close-in-zone retrace | 50.5% | ~62% | Filtered wick-only touches |
| Displacement check | ~62% | ~64% | Filtered weak events |
| Structure TP + ATR min | ~64% | 66.0% | Better exits |
| Final filtered | 66.0% raw → 94.7% top10k | — | — |

## SL/TP Format Pitfall

Frontend expects SL as percentage (sl_initial_pct, sl_pct), NOT absolute price.
Backend stores SL as absolute price (zone_low - ATR_buffer).
Adapter must convert: `sl_initial_pct = (entry_price - sl) / entry_price * 100`

Symptom of wrong format: SL column shows 0.1% or 14.12 (price instead of %).

## Frontend Sync Checklist

After V27 scan:
1. `reload_trades()` — V27 first, then V26/V25 fallback
2. `reload_picks()` — V27 first
3. `ver_map` — add 'V27': _vdata('/root/.hermes/smc_opt_v27/v27_trades.json')
4. Nav brand — replace all 'V26' → 'V27' (replace_all)
5. Title — 'V21 Dashboard' → 'V27 Dashboard'
6. Clear __pycache__
7. Restart: `python3 -u smc_unified.py`
8. Verify: curl all pages return HTTP 200

## Frontend Massive Data Pitfall

If trades JSON >100MB, `build_dashboard()` loading 10k+ trades can time out.
The server appears to listen (ss shows LISTEN) but returns empty responses (HTTP 000).

**Fix**: Filter trades to ≤10,000 entries, keep JSON under 10MB.
Never let raw scan output (200k+ trades) reach the frontend without filtering.

**Symptom chain**:
1. `ss -tlnp | grep 8890` shows LISTEN ✓
2. `curl http://127.0.0.1:8890/` returns empty (HTTP 000) ✗
3. Import works, `build_dashboard()` works standalone ✓
4. Server binary runs, prints banner ✓
5. But HTTP handler times out reading/processing huge JSON
→ Filter the data, don't debug the server.
