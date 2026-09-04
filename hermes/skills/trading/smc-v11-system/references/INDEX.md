# SMC references index

This index exists because `SKILL.md` is already near the Hermes size limit; add new session-specific details here when patching the main skill is blocked by size.

## Execution / frontend contract references
- `v66-field-contract-frontend-sync.md` — front-end field contract basics.
- `v66-monitor-live-field-contract-verification.md` — `/monitor` and `/live` zero-blank field verification.
- `v85-bear-risk-reversal-suppression.md` — BEAR_RISK SSL→CHOCH candidate promotion fix.
- `v88-live-execution-entry-contract.md` — live execution must not use historical contract prices; trading-hours fill uses live price, after-hours waits pending, stale picks are WATCH_ONLY, and V88 zone-limit backtest entries must be executable on entry day.
- `v105a-scanner-time-contract.md` — V105-A showed a historical secondary audit can improve WR/SL, but promotion is blocked if the real full-market scanner cannot compute selector fields (`v100_tier`, `mtf_trend_permission`, `tp2_target_type`, `sl_mode`, `tp2_rr`, etc.) before BUY without outcome leakage.
