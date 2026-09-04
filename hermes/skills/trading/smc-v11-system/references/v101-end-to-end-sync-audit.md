# V101 End-to-End Frontend Sync + Trade Audit Lessons

Use this reference when promoting a new SMC contract layer or auditing whether backtest/selection/live/K-line/analysis/autopsy/docs are truly synchronized.

## Trigger
- User asks whether all data is synchronized to frontend surfaces.
- A new contract layer adds fields such as MTF state, SMC DNA, combo contracts, pick/join dates, zone/cost/volatility.
- Backtest stats look correct but visual pages or APIs may still show stale version labels or missing fields.

## Required verification sequence
1. Verify authoritative output files first: `v*_trades.json`, `v*_active_picks.json`, `v*_report.json`, DNA/contract files.
2. Programmatically check `/api/picks` and `/api/live-prices` for core field missing counts before trusting page display.
3. Browser-check each user-facing surface: `/monitor`, `/live`, `/backtest`, `/analysis`, `/autopsy`, `/docs`, `/kline?s=...`, `/resonance`, `/logs`.
4. Treat page source hits for `undefined`/`NaN` carefully: confirm actual rendered DOM/browser snapshot before calling it a user-visible bug.
5. Verify K-line version badge separately: JS may overwrite the template label after `/api/kline_full` returns a routing-shell version such as V88.
6. After patching output contracts or frontend fields, regenerate the engine output, restart `smc_unified.py`, then re-query APIs and browser pages.

## Field contract checklist
Core cross-surface fields should include:
- Dates: `pick_date`, `join_date`, `entry_date`, `exit_date` when realized.
- Identity: `engine`, `signal_type`, `conf_type`, `signal_price`.
- Trade geometry: `zone`, `zone_type`, `zone_low`, `zone_high`, `cost_line`, `smart_money_cost`, `volatility_pct`.
- Risk/targets: `entry_price`, `sl`, `tp1`, `tp2`, `tp3`, `risk_pct`, `exit_reason`, `hold_bars`.
- MTF: `weekly_state`, `daily_state`, `m60_state`, `mtf_stage`, `mtf_trend_permission`, `mtf_conflict_state`.
- DNA/combos: `smc_dna`, `dna_preferred_behavior`, `dna_effective_entry_mode`, `dna_effective_combo`, `combo_contract_key`, `combo_family`, `combo_contract`.

## Pitfalls found
- `hold_bars` may be a placeholder while `hold_bars_realized` has the real value. Normalize `hold_bars` from `hold_bars_realized` or from `exit_idx-entry_idx` before doing entry/exit timing analysis.
- Missing `conf_type` and `signal_price` in a contract layer breaks K-line/backtest/API consistency even when the signal itself exists. Backfill from `signal_type/source_event/event_type` and `break_level/price/entry_price`.
- `/api/live-prices` often rebuilds rows from monitor/pick state, not directly from trades. It needs explicit pass-through for contract fields, not just `_apply_smc_field_contract` on the pick.
- Docs can remain stale even when APIs are correct. Update `/docs` production-contract text whenever a version is promoted.
- A routing shell such as V88 can correctly serve V101 files, but the displayed badge must use the promoted frontend version to avoid false “not synced” diagnosis.

## Analysis standard
Do not stop at aggregate WR/RR. Produce:
- Full count: all trades, production trades, candidate pool, active picks, DNA symbols, T+1 violations.
- Yearly stats: n, net WR>=0.8, avg/median net, SL rate, avg/median hold, TP hit rate.
- Entry audit: zone position distribution, entries before event, entries too late after event, entries above/below zone.
- Exit audit: TP/SL counts, SL rows with prior MFE, TP exits with MFE beyond TP3/runner threshold.
- Explicit “observed problems” and “not observed” findings.

## Next-step diagnosis pattern
If production WR is high but average return is capped, test exit-contract changes first; do not disturb validated entry logic. If a candidate combo has high SL rate, audit signal correctness before parameter tuning or promotion.
