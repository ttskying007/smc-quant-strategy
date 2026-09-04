# V102 full-backtest audit: no-future-function gate

Session lesson from the V102 production backtest audit:

- Do not rely only on aggregate `t1_violations` or raw production stats. A production row can still contain a future-looking SMC component even when the trade entry/exit dates pass T+1.
- For every production trade, audit all pre-entry SMC components against the actual `entry_date` / `entry_idx`:
  - `pick_date`, `select_date`, `event_date`, `signal_date`, `conf_date`, `confirm_date`
  - `join_date`
  - `zone_date` and especially `zone_idx`
  - `structural_sl_ref.idx/date`
  - every `structural_targets[].idx/date`
- Hard failure rules:
  - any pre-entry event date > `entry_date`
  - any pre-entry event index > `entry_idx`
  - `exit_date <= entry_date` for A-share T+1
  - any chosen structural target or SL reference with idx/date after entry
- If a violation appears, do not bury it inside the summary. Export both:
  1. raw production report including the violating rows;
  2. clean no-future report with the violating rows excluded.
- The detailed CSV should include enough fields for manual chart inspection:
  - symbol, pick/signal/join/zone/entry/exit dates
  - event_idx, zone_idx, entry_idx, exit_idx when present
  - signal/conf type, zone type/range, cost line, volatility
  - entry price, exit price, exit reason, net pnl, risk, SL, TP1/TP2/TP3, planned exit legs
  - `structural_sl_ref` and first structural targets with type/date/price/RR
- Useful report shape:
  - yearly clean stats
  - combo-contract clean stats
  - `future_function_violations.csv`
  - `production_operations_clean_no_future.csv`
  - `smc_event_sequence.csv`

Concrete V102 finding: one production row (`000045.SZ`) had `zone_idx=636` after `entry_idx=634` and `zone_date=2025-12-23` after `entry_date=2025-12-19`. It was removed from the clean no-future-function production口径. Treat this as a recurring audit pattern, not a one-off stock-specific rule.
