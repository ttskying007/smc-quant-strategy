# V185 active pick lifecycle contract repair

Use when V185 production is kept but active picks look stale, have blank SL/TP, or frontend/live-prices show missing risk fields.

## Symptom

- `v185_active_picks.json` can contain current dry-run rows without explicit `sl/tp1/tp2/tp3/rr`.
- `bars_since_entry` may remain at scanner-time values while local K-line cache advances.
- Historical V185 trades are valid, but active candidates need non-outcome execution-contract materialization for frontend/live monitoring.

## Fix pattern

Patch/run `/root/.hermes/scripts/v25/v185_daily_rematerialize.py` so `normalize_active_row()` materializes only pre-entry/design fields, never realized outcome fields:

- `sl = zone_low * 0.99` per V185 contract `SL=zone_low-1%`.
- recompute `risk_pct/sl_pct/volatility_pct` from actual executable `sl`.
- `tp/tp1/tp2/tp3 = entry_price + (entry_price - sl) * 1.5`.
- `rr/r_mult = 1.5`, `max_hold = 10`.
- `cost_line/smart_money_cost = midpoint(zone_low, zone_high)`.
- update `bars_since_entry`, `latest_kline_date`, `latest_close`, `unrealized_pnl_pct` from `/root/.hermes/kline_cache/*_daily_750.json` using T+1 bars (`date > entry_date`).
- preserve/blank realized outcome fields (`exit_date`, `pnl_pct`, `won`, `mfe_pct`, etc.) so active picks remain unpolluted.

## Verification

Run:

```bash
cd /root/.hermes/scripts/v25
python3 -m py_compile v185_daily_rematerialize.py v313_v185_active_pick_lifecycle_audit.py
python3 v185_daily_rematerialize.py
python3 v313_v185_active_pick_lifecycle_audit.py
python3 v312_production_shadow_branch_checkpoint.py
curl -sS --max-time 5 http://127.0.0.1:8890/api/live-prices | head -c 1000
```

Pass conditions:

- `active_outcome_pollution=0`.
- V313 `missing_contract_rows=0` and `stale_bars_rows=0`.
- V312 `release_gate.can_claim_current_production_closed=true`.
- `/api/live-prices` rows expose `sl`, `tp1`, `tp2`, `tp3`, `rr`, current/last price, pick/join dates.

## Pitfall

Do not derive `risk_pct` as `(entry-sl)/entry` if the rest of V185 uses `entry/sl-1` style; keep it consistent with the historical artifacts or the displayed RR/SL percentage will drift from the execution contract.
