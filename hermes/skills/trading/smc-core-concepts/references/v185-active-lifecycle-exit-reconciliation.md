# V185 active lifecycle exit reconciliation

Use this when active/current picks look stale, negative, or still displayed after TP/SL should have triggered.

## Durable lesson

An active watchlist is not valid just because rows are current candidates and have non-empty SL/TP fields. It must be mechanically replayed under the production execution contract on every rematerialization:

1. Normalize active rows and materialize pre-entry contract fields (`entry_price`, `sl`, `tp1`, `max_hold`, `zone_low/high`).
2. Replay each active row against local K-line cache using **T+1 only** bars (`date > entry_date`).
3. Apply the same executable contract shown to the frontend:
   - SL
   - TP / TP1
   - max_hold TIME close
   - conservative daily-bar ambiguity: if SL and TP both touch in one bar, count SL first.
4. Rows that already hit SL/TP/TIME must be removed from `active_picks` / `picks` and archived separately as reconciled active closes.
5. Re-run lifecycle audits after rematerialization; expected result after reconciliation can legitimately be `active_count=0`.

## Anti-pattern caught

`v185_daily_rematerialize.py` originally only normalized active fields and rewrote `v185_active_picks.json`. It did **not** replay active rows through the V185 contract. This left 6 stale rows in active view even though all had mechanically closed:

- 5 TP
- 1 SL
- 0 T+1 violations

This produced misleading downstream states such as `STALE_REVIEW_NEEDED` and `ZONE_DEAD_UNRECOVERED` even though the correct action was active reconciliation, not strategy adjustment.

## Correct artifact pattern

- Keep active rows outcome-free.
- Archive reconciled active exits separately, e.g. `v185_reconciled_closed_active.json`.
- Preserve the archive across later rematerializations; do not overwrite it with `[]` just because current active is empty.
- Empty active is valid and must not raise a missing-active error.
- If active is empty, keep `latest_market_date` from archive/report where available rather than blanking it.

## Verification gate

After any active lifecycle repair, run the full chain:

```bash
python3 /root/.hermes/scripts/v25/v185_daily_rematerialize.py
python3 /root/.hermes/scripts/v25/v312_production_shadow_branch_checkpoint.py
python3 /root/.hermes/scripts/v25/v313_v185_active_pick_lifecycle_audit.py
python3 /root/.hermes/scripts/v25/v314_v185_active_executable_exit_audit.py
```

Pass condition:

- `active_outcome_pollution = 0`
- `same_day_exit_violations = 0`
- active rows that should close by contract are no longer in active/picks
- `v313` reports either valid active lifecycle states or `NO_ACTIVE_ROWS`
- `v314` reports no remaining mechanical close required after reconciliation

## Naming convention

For this class of check, use a no-write audit script first, then patch rematerialization only after the audit proves the active rows should close. Suggested pattern:

- `vXXX_active_executable_exit_audit.py` for no-write proof
- `*_reconciled_closed_active.json` for archived closes
