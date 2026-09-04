# Daily full-market selection + live fallback verification

Session lesson: production daily picks must be generated from the latest full-market K-line cache, while historical trade files remain validation/replay inputs only.

## Production source contract

- Daily production scan source: `/root/.hermes/kline_cache/*_daily_750.json` latest market date.
- Historical files such as `v65_trades.json` / `v66_trades.json` are allowed only for backtest, replay, autopsy, and gate validation.
- Production pick rows should carry `source='full_market_kline_scan'`, `engine='V66_FULL_MARKET_SCAN'`, and date fields: `pick_date`, `select_date`, `entry_date`.
- When current full-market scan rows exist in `v66_picks.json`, frontend merging must not also prepend `v66_daily_candidates.json`; otherwise rejected/duplicate diagnostic rows leak into `/api/picks`.

## PINBAR quarantine

- Do not promote `OB → PINBAR` or `Sweep → OB → PINBAR` into `/api/picks`, `/monitor`, `/live`, positions, or ledger.
- If a scan path encounters PINBAR sequences, mark them rejected/validation-only, e.g. `PINBAR_SEQUENCE_BLOCKED`.

## Join-date contract

- `join_date` comes from lifecycle state (`positions.json.created_at`) when a candidate has been imported/monitored.
- Use all positions, not only `OPEN`, to backfill join dates for closed/imported historical lifecycle rows.
- API and monitor page should both expose non-blank join dates for current production candidates.

## Live page fallback pitfall

When `_api_live_prices()` normalizes monitor positions, it may synthesize V25 fields (`v25_sl_price`, `v25_sl_pct`, `v25_tp_tiers`) for old positions. That forces the V25 branch even when old rows lack `v25_cost_line` / `v25_vol_class`.

Use fallback inside the V25 branch too:

```python
cost_line = p.get('v25_cost_line') or p.get('smart_money_cost') or p.get('cost_line') or entry_price
vol_class = p.get('v25_vol_class') or p.get('market_state') or p.get('regime') or p.get('quality_tier') or (f"RISK {float(sl_pct):.1f}%" if sl_pct else p.get('zone_type', ''))
```

Verification gates after any daily-task repair:

- `python3 v25/smc_closed_loop_ops.py selftest`
- `python3 v25/smc_closed_loop_ops.py daily`
- `python3 v25/smc_closed_loop_ops.py live --force`
- `python3 v25/smc_closed_loop_ops.py postmarket`
- `/api/picks`: full-market rows only, PINBAR=0, join_blank=0, engine_blank=0, zone_blank=0.
- `/api/live-prices`: PINBAR=0, `costLine` blank/zero=0, `volClass` blank=0.
- `/monitor` and `/live` browser check: columns render dates/cost/volatility visibly.
