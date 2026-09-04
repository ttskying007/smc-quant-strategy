# V66 Historical Pollution Quarantine Pattern

## Trigger
Use this when an SMC live-monitor/backtest discrepancy keeps showing old stop-loss failures after `sample_class=DIAGNOSTIC_ONLY` or provenance/T+1 fixes were already applied.

## Durable Lesson
Tagging polluted samples is not enough if downstream dashboards, daily ops logs, release gates, or review pages still read the same production JSON files. Historical pollution must be both:

1. **Logically labeled** — `sample_class=DIAGNOSTIC_ONLY`, root cause, issue flags.
2. **Physically quarantined** — closed diagnostic rows moved out of production `positions.json`, `closed_reviews.json`, and trade ledger production view.

## Failure Mode Observed
Previous fixes normalized provenance and labeled diagnostic samples, but `closed_reviews.json` and `positions.json` still contained old closed diagnostic rows. The UI and reports continued to read those files, so the user still saw historical SL pollution. A further cache layer (`ops_latest.json`) also kept showing old review counts after the production files were corrected.

## Required Repair Sequence
1. Back up monitor state before mutation.
2. Move `CLOSED` non-`PRODUCTION_CLEAN` positions to a quarantine directory.
3. Move non-`PRODUCTION_CLEAN` closed reviews to quarantine.
4. Move ledger rows linked to quarantined positions, invalidated rows, or diagnostic rows to quarantine.
5. Keep legacy `OPEN`/`WATCH_ONLY` positions visible for risk monitoring, but exclude them from production WR/SL metrics.
6. Add release-gate checks that fail if production review files contain diagnostic closed rows.
7. Refresh any cached ops/dashboard state (`ops_latest.json`) after file-level quarantine.
8. Browser-verify the live/log pages: production review count, closed count, ledger count, and visible text must match the new source files.

## Verification Contract
A repair is not complete until all of these are true:

- `closed_reviews.json` contains only `PRODUCTION_CLEAN` rows, or is empty.
- `positions.json` has no `CLOSED` rows with `sample_class != PRODUCTION_CLEAN`.
- Release gate includes and passes `production_reviews_clean_only` and `production_closed_positions_clean_only`.
- Daily ops/log page separates `active_tradable_count` from `watch_only_count`.
- Logs page no longer displays archived historical SL symbols.
- Reports explicitly state that clean live WR/SL cannot be compared to backtest WR until new clean closed samples exist.

## Reporting Language
When production clean closed samples are zero, do not claim the strategy is fixed or validated in live trading. State: backtest gates pass, historical pollution is quarantined, and live clean-vs-clean validation is pending future clean closed samples.
