# V49 exit optimization lessons

- V49 keeps V48.1 signal/entry universe unchanged and only changes exit mechanics.
- Best grid candidate from 864 tests: `max_hold=240`, `tp1_frac=0.05`, `tp2_frac=0.05`, `tp1_r=1.5`, `tp2_r=3.2`, `breakeven_r=1.0`, `breakeven_bars=3`, `trail_trigger_r=18`, `trail_lock_r=2.0`.
- Compared with V48.1 on the same 132 trades: WR unchanged 88.64%, SL unchanged 10.61%, avg_pnl improved 11.961% -> 15.110%, total_pnl 1578.83 -> 1994.53, avg_win 14.04 -> 17.597.
- Deep cause: V48.1 used 10%/10% partials and 12R/1.2R runner trailing; this exited large runners too early. V49 reduces partials to 5%/5% and delays/widens trailing to 18R/2R so 90% runner survives.
- Tradeoff: sold_early_rate stays ~74.24% and avg_mfe_capture is not improved because post-exit 30-bar explosive continuation remains; optimizing that further requires regime/structure-based runner logic, not a single trailing parameter.
- Promotion checklist same as V48.1: add V49 to `ACTIVE_VERSION`, trade/pick paths, `get_version_trades/picks`, `_active_version_paths`, API summary req_ver maps, Kline ver_map/dropdown, backtest engine_map, docs, monitor/analysis/autopsy; verify `/api/summary`, `/api/kline_full?ver=V49`, `/monitor`, `/backtest`, `/docs`.
