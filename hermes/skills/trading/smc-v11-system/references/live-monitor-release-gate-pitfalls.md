# SMC live monitor release-gate pitfalls

Use this reference when repairing or auditing SMC production monitor / V66+ release gates.

## Distinguish three layers

Do not collapse these into one pass/fail result:

1. **Backtest layer** — `v66_trades.json`, T+1 exit audit, signal sequence/provenance audits.
2. **Live execution layer** — `positions.json`, `trade_ledger.json`, live OPEN/WATCH_ONLY state, T+1 entry, Zone lifecycle, cost/vol fields.
3. **Sample coverage layer** — latest full-market scan candidates, active/watch/rejected funnel, clean-vs-diagnostic sample population.

A backtest gate passing does not prove live execution is safe. A live execution gate passing does not prove sample coverage is adequate.

## Live execution hard gates

Expected checks in `v66_live_execution_audit.py`:

- `live_t1_no_same_day_fill=true`
- `ledger_t1_no_same_day_buy=true`
- `open_zone_complete=true`
- `open_cost_line_complete=true`
- `open_vol_class_complete=true`
- `open_zone_valid=true`
- `watch_only_has_reason=true`
- `clean_provenance_complete=true`

If any same-day BUY/fill is found, do not delete it silently. Mark ledger events `invalidated=true` with a reason, repair positions back to `NEXT_DAY_PENDING` or `WATCH_ONLY`, and keep backups under `~/.hermes/smc_monitor/backups/`.

## Sample-bias audit pitfall

`ACTIVE_ENTRY_TOO_NARROW` can be a real strategy warning or an audit-mouth bug.

For V66 full-market daily picks, active rows may use:

- `pick_scope == 'ACTIVE_CANDIDATE'`
- `pick_scope == 'ACTIVE_ENTRY'`
- `is_active_pick == true`

Do not count only `ACTIVE_ENTRY`; that falsely reports `active_entry_count=0` when the current production scanner emits `ACTIVE_CANDIDATE`.

Correct active definition:

```python
active = [
    p for p in picks
    if p.get('is_active_pick')
    and p.get('pick_scope') in ('ACTIVE_CANDIDATE', 'ACTIVE_ENTRY')
]
```

## Provenance field contract

`daily_scan.py` / full-market scan may emit `zone_bar`, `entry_idx`, `zone_date`, and `confirm_date`, while monitor classification may expect `zone_idx` and `conf_index`.

Before classifying a new production row as clean/diagnostic, normalize equivalent fields:

- `zone_idx = zone_idx or zone_bar`
- `conf_index = conf_index or conf_idx or confirm_idx or entry_idx - 1`
- preserve `entry_idx`, `zone_date`, `confirm_date`, `entry_date`
- preserve `zone_low/zone_high`, `cost_line/smart_money_cost`, `vol_class/v25_vol_class`

Otherwise fresh, valid production rows are incorrectly marked `DIAGNOSTIC_ONLY` with `MISSING_PROVENANCE`, keeping `production_clean_count=0` forever.

## Candidate coverage interpretation

If latest full-market scan has many rejected rows, do not directly relax buy gates.

Example V66 pattern:

- latest candidates: 105
- active: 3
- rejected: 102
- rejected reason included `RISK_GT_5` for all rejected rows
- rejected risk p50 ≈ 17%, active risk ≈ 4%

This means the scanner found setups, but the executable risk is too wide. The safe repair is **watchlist expansion**, not active buy expansion:

- keep `ACTIVE_CANDIDATE` for executable rows only
- add `NEAR_ZONE_WATCH` / `HIGH_RISK_WATCH_ONLY` for rejected-but-interesting rows
- show them in UI/push reports as observation only
- exclude them from trade ledger BUY events and production-clean performance stats

## Reporting standard for Lei

For SMC repair reports, use compact tables with explicit counts and status. Separate:

- fixed execution defects
- audit false positives
- true strategy/coverage limits
- deferred items needing full backtest or new-version validation

Avoid presenting rejected high-risk candidates as a quick win. Signal correctness and executable quality outrank broader trade count.
