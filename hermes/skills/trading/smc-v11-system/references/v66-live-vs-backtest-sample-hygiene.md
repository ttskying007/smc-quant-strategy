# V66 live-vs-backtest sample hygiene and watch-only funnel

Session lesson from V66 realtime monitoring repair: when live stoplosses look far worse than backtest, first split the population by sample class before changing signals, entries, SL, or TP.

## Root-cause sequence

1. Run live execution and sample-bias audits before strategy tuning.
2. Separate `PRODUCTION_CLEAN` from `DIAGNOSTIC_ONLY` in positions, ledger, and closed reviews.
3. Treat manual/imported/stale picks as diagnostic only; do not compare their SL rate directly with backtest WR.
4. Normalize field provenance at the monitor boundary: `zone_bar -> zone_idx`, `entry_idx/confirm_idx/conf_idx -> conf_index`, `confirm_date -> conf_date`.
5. Keep active-buy scope separate from observation scope: high-risk candidates should become `WATCH_ONLY`, not executable `ACTIVE_CANDIDATE`.
6. Update release gates to check both tradable active count and observation coverage, plus clean provenance completeness.

## Practical checks

- `v66_sample_bias_audit.py` should count `ACTIVE_CANDIDATE`, `ACTIVE_ENTRY`, and `is_active_pick`; checking only `ACTIVE_ENTRY` creates false `ACTIVE_ENTRY_TOO_NARROW` failures.
- `v66_live_execution_audit.py` should report `production_clean_count`, `polluted_count`, and `clean_missing_provenance` separately.
- `/api/picks` should show active + watch-only candidates, but `ingest_daily_picks()` should only buy `ACTIVE_CANDIDATE` rows with `is_active_pick=true`.
- Daily review summaries should include `production_clean_reviews`, `diagnostic_reviews`, `clean_reason_counts`, and `diagnostic_root_cause_counts`.

## Interpretation rule

If closed live reviews are all `DIAGNOSTIC_ONLY`, the correct conclusion is "production live sample is not yet comparable to backtest," not "SL/TP must be widened." Only after clean live samples accumulate should the next autopsy judge single SMC signal accuracy, combined signal path, entry-zone distance, T+1 execution drift, and structural SL placement.
