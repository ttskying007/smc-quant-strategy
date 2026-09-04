# V48.1 production promotion lessons

- V48.1 keeps V47.2 verified signal definitions; do not change Pine/LuxAlgo signal source when repairing exits.
- Promotion surfaces in `smc_unified.py`: `ACTIVE_VERSION`, `ACTIVE_TRADE_FILE`, `ACTIVE_PICK_FILE`, `get_version_trades/picks`, `_active_version_paths`, `/api/summary` req_ver branch, Kline ver_map/default dropdown, `/api/backtest/run` engine_map, docs, monitor, analysis/autopsy.
- V48 fills `signal_price`; V48.1 filters weak `ZONE_MID_EXECUTABLE` trades with `raw_zone_width_pct >= 4`.
- In partial-exit systems, `exit_price`/`exit_price_effective` is a weighted effective price and may not lie in the final exit bar. Executability audit must check `exit_price_final` plus every `exit_legs[].price`.
- Trailing stops can sit slightly outside a restored/fq bar range after gap/rounding. Clamp stop execution to `[low, high]` and record `stop_executed_clamped`; otherwise P0 audit reports `LEG_PRICE_OUTSIDE_BAR`.
