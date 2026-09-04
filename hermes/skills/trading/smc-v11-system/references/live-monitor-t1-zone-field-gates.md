# Live monitor T+1 / Zone / Field gates

When fixing SMC production monitor issues, distinguish backtest compliance from live execution compliance.

## Hard rules

- Backtest `v66_t1_audit.py` passing does **not** prove live monitor T+1 is safe.
- Live positions and trade ledger must also satisfy:
  - `filled_at_date > pick_date` for OPEN/CLOSED production positions.
  - BUY ledger `buy_date > pick_date/select_date`.
  - SELL `sell_date > buy_date`.
- Same-day picks must stay `NEXT_DAY_PENDING` with `pending_reason='SAME_DAY_PICK_NO_BUY'` even if the market is open.
- `fill_pending_orders()` must re-check T+1 immediately before setting `OPEN`/`filled_at`.

## Zone lifecycle gate

Before pending -> OPEN, recalculate live execution price vs zone:

- Missing `zone_low/zone_high` => no clean production sample.
- Bull price below zone beyond threshold => WATCH_ONLY (`PRICE_BELOW_ZONE_*`).
- Price too far above zone => WATCH_ONLY (`PRICE_ABOVE_ZONE_*`).
- Store `entry_zone_relation`, `entry_zone_distance_pct`, and `production_gate` on the position and ledger.

## Sample classes

Closed/live review stats must separate:

- `PRODUCTION_CLEAN`
- `PENDING_T1`
- `DIAGNOSTIC_ONLY`
- legacy/manual/imported/stale/missing-provenance samples

Do not use polluted/legacy samples to judge strategy signal quality or SL/TP design.

## Frontend/API field contract

`/api/picks` and `/api/live-prices` must expose stable fields:

- dates: `pickDate/select_date`, `joinDate/join_date`, `entryDate`
- zone: `zoneType`, `zoneLow`, `zoneHigh`, `entryZoneRelation`
- execution: `costLine`, `volClass`, `productionGate`

The live table should show 选股日、加入日、买入日、成本线、Zone、波动. Invalidated BUY events may remain in `/api/trade-ledger` for audit but should be hidden from the main live-page ledger.

## Verification commands

```bash
cd /root/.hermes/scripts
python3 -m py_compile smc_monitor_state.py smc_unified.py v25/v66_live_execution_audit.py v25/v66_release_gate.py
python3 v25/v66_live_execution_audit.py
python3 v25/v66_release_gate.py
```

Expected live audit checks:

- `live_t1_no_same_day_fill=true`
- `ledger_t1_no_same_day_buy=true`
- `open_zone_complete=true`
- `open_cost_line_complete=true`
- `open_vol_class_complete=true`
- `open_zone_valid=true`
- `watch_only_has_reason=true`
