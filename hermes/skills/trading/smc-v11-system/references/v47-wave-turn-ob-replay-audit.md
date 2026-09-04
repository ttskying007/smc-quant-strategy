# V47 SMC Wave-Turn OB / Replay Audit Lessons

Context: V47 repair work exposed another class of SMC failures where the detector was partially fixed, but backtest/watchlist/frontend outputs silently lost the fields needed to prove the fix was actually used.

## Durable lessons

1. **OB correctness is not just count reduction.** A valid OB must be anchored to a confirmed wave turn (`HH/HL/LH/LL`) and carry that proof through every downstream artifact.
   - Required OB fields: `wave_turn_idx`, `wave_turn_date`, `wave_turn_label`, `wave_turn_price`, `wave_turn_distance`, `anchor_method`, and preferably `source_signal`.
   - Bull OB should anchor to demand-side turns (`HL/LL/L`); bear OB should anchor to supply-side turns (`HH/LH/H`).
   - Reject or flag any OB trade/pick that lacks `wave_turn_label`, even if aggregate WR/RR improved.

2. **Preserve source explainability from detector → zone → setup → trade → watchlist → frontend.**
   - The V47 issue was not the core OB detector after repair; it was field loss in the V45/V46 bridge.
   - When a function converts a signal into a zone, copy `source_signal` and `wave_turn_*` / `gap_*` fields immediately.
   - When `backtest_v34_setups()` or another replay layer returns merged trades, restore/verify source fields by matching setup keys such as `entry_index`, `zone_idx`, and `zone_type`.

3. **Every full rebuild needs a contract audit before reporting completion.** Minimum checks:
   - report count == kept trades count
   - OB trades: 100% have `wave_turn_label`
   - FVG trades: 100% have `gap_low/gap_high` and source three-candle indexes when available
   - trade timeline order: `signal_idx <= conf_idx <= entry_idx <= exit_idx`
   - entry/exit prices lie inside the corresponding day's high/low
   - active picks come from watchlist/current candidates, not historical trades
   - `/api/kline_full` returns `wave_swings` and rendered zones carry the same source fields as trades/picks

4. **Do not trust replay-only RR experiments as production results.** They are useful to identify direction, not to replace engine logic.
   - In V47 replay diagnostics, `zone_mid + structural SL` sharply reduced sold-early/fake-SL symptoms versus exec-high/current-SL, but this must be implemented in the setup engine and rerun full-market before acceptance.
   - Keep the distinction explicit: “replay diagnostic” vs “production backtest”.

5. **FVG auditing must follow the pine-like source path.** A LuxAlgo-core scan returning zero FVGs does not mean the system has no FVGs if FVGs are produced by `smc_core_pine_like.py` / V41 paths. Audit the same source used by backtest and frontend.

## Suggested audit script shape

A reusable V47-style audit should produce:

```json
{
  "output_audit": {
    "counts": {},
    "field_coverage": {},
    "failures": []
  },
  "current_signal_audit": {
    "signal_counts": {},
    "ob_wave_bad_count": 0
  },
  "trade_autopsy": {
    "summary": {},
    "sample_failures": []
  },
  "frontend_contract": {
    "ok": true,
    "failures": []
  }
}
```

P0 failures include:
- `OB_TRADE_MISSING_WAVE_TURN_LABEL`
- `FVG_TRADE_MISSING_GAP_BOUNDS`
- `TRADE_TIMELINE_VIOLATION`
- `ENTRY_PRICE_OUTSIDE_BAR`
- `EXIT_PRICE_OUTSIDE_BAR`
- `FRONTEND_MISSING_WAVE_SWINGS`
- `PICKS_FROM_HISTORICAL_TRADES`

## Files touched in the V47 pattern

Typical files for this class of repair:
- `v25/smc_core_luxalgo_v34.py` — wave-turn OB detector and `wave_swings`
- `v25/v45_1_recall_repair.py` — detector/zone/setup/trade/watchlist field propagation
- `v25/v46_1_layered_3y.py` — full rebuild and kept/rejected output bundle
- `smc_unified.py` — `/api/kline_full`, `/api/picks*`, frontend chart overlay contract
- `v25/audit_v47_smc_system.py` — deterministic audit runner
- `v25/v47_entry_sl_exit_experiments.py` — replay-only entry/SL/exit diagnostic

## Completion wording rule

Only say the SMC repair is complete after:
1. full-market rebuild finished after the latest code change;
2. audit reports no P0 failures;
3. frontend contract has been checked via HTTP or browser;
4. sample visual K-line overlays match the same signal IDs/fields used by trades and picks;
5. replay diagnostics, if used, have been productionized and rerun full-market.
