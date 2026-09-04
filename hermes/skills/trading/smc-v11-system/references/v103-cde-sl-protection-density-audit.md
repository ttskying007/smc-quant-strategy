# V103-C/D/E SL Replay, Protection Grid, and Candidate Density Audit

## Trigger
Use this when continuing V103+ SMC production audits after a risk/field-contract gate is already live, especially when the remaining issue is residual SLs, late profit giveback, or month/candidate crowding.

## Durable workflow

1. **Do not keep tuning the entry gate once V103-A-style risk gate passes.**
   - Freeze the production population first: `production_eligible_v102 == true`, `future_leak_flag != true`, and the new gate flag (e.g. `v103a_risk_gate == true`).
   - Recompute V102 vs current from the files, not from stale report text.

2. **V103-C: replay every SL, not just aggregate SL rate.**
   - Compare baseline SL rows against post-gate production rows by a stable key such as `symbol|entry_date|select_date|combo_contract_key`.
   - Output two artifacts: all baseline SLs with removed/kept status, and residual current SLs.
   - Useful buckets:
     - `V103A_FILTERED_LOW_RISK_NOISE`: solved by the risk gate.
     - `BREAKEVEN_AFTER_1R_MISSING`: reached at least 1R then fell to SL.
     - `LATE_PROTECTION_MISSING_PROFIT_GIVEBACK`: hold > 10 and MFE >= 2R before SL.
   - Keep the per-row fields: symbol, select/entry/exit dates, hold bars, MFE_R, MAE_R, risk_pct, net_pnl_pct, conf_type, zone_type, market_state, TP2_R, expected TP2 net.

3. **V103-D: run a bar-path protection grid before changing production exits.**
   - MFE summary alone is insufficient; load the matching daily K-line cache and replay from `entry_idx+1` to `exit_idx`.
   - Enforce T+1 and activate any new stop only from the next bar after trigger.
   - Test at least these conservative variants:
     - `BE_1R_HOLD10`: after hold >= 10 bars and price reaches entry + 1R, protect at entry.
     - `TP1_LOCK_HOLD10`: after hold >= 10 bars and price reaches TP1, protect at TP1.
     - `HALF_TP1_LOCK_HOLD10`: after hold >= 10 bars and price reaches TP1, protect at halfway from entry to TP1.
   - Report SL rate, net WR >= 0.8%, average net PnL, changed trade count, and changed rows.
   - Do **not** promote a rule just because SL rate improves. If average net PnL drops or good TP2 winners are cut early, leave it as a candidate.

4. **V103-E: candidate density is an audit/display field first, not a hard filter.**
   - Count current gate candidates by select/pick month.
   - Add density labels from quantiles (e.g. P50/P80/P95) and sidecar-enrich active picks.
   - Do not hard-filter high-density months without per-SL replay evidence; high density can include strong production months.

5. **Front-end field contract verification remains mandatory after any V103 audit update.**
   - `/monitor`: selection date, join date, Zone, cost line, volatility must be visible and non-empty.
   - `/live`: same fields plus last-price fallback state must distinguish true empty from market-closed/no-live-price.
   - Active pick fields to count as release gates: `pick_date`, `join_date`, `zone_type`, `smart_money_cost`, `volatility_pct`, `engine`.

## Production decision rule
Only promote a V103-D exit protection when it improves SL rate and net WR without materially reducing average net PnL or cutting high-quality TP2/TP3 winners. Otherwise, output the grid and keep production unchanged.

## Session artifact pattern
Good output files for this class of task:
- `v103cde_deep_audit.json`
- `v103cde_deep_audit_report.md`
- `v103cde_sl_replay_24.csv` (or equivalent baseline SL count)
- `v103cde_residual_sl_19.csv` (or equivalent current residual SL count)
- `v103e_month_density.csv`
- `v103cde_active_picks_enriched.json`
- `v103d_protection_rule_grid_barpath.json`
