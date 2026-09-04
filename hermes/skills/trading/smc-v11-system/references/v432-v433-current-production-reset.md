# V432/V433 current-production reset and fail-closed refresh

Use when historical V185/V365 results are proposed as current production or when refresh success is inferred from HTTP/request success alone.

## Provenance correction

- V432 rejects V185 as a production baseline: V175 entries precede takeover-2/3 confirmation and the child lineage uses post-reclaim bars without complete provenance indices.
- V185 history may remain research evidence, but current `active_picks` and `picks` must be empty until a new raw scanner passes causality.
- V366 rejects the apparent V365 survivor for early entry; V367 causal replay has zero common OOS survivors.
- V433 is therefore a negative-control shadow only: `production_write=false`, `frontend_write=false`, `watchlist_write=false`, `buy_enabled=false`.

## Refresh gate

Do not define freshness as successful provider responses. Require all of:

1. request success coverage >=90%;
2. modal/latest market-date coverage >=99% of the requested universe;
3. latest date does not regress;
4. latest date is not in the future;
5. latest date age <=4 calendar days.

Write explicit `gate_failures`. Any failure exits nonzero and downstream production must skip scanner, candidate generation, and ingest.

## Operational isolation

After data refresh passes, run V433 independently even if V185 causality fails. Record its report in the daily ops log, but never convert it into a pick. On V185 causality failure, the expected result is:

- pipeline state `FAIL_CLOSED_V185_CAUSALITY`;
- `daily_ingest.added=0`;
- V185 active/picks files equal `[]`;
- `/api/picks` empty;
- V433 still reports no-write/no-buy.

## Next architecture

A legitimate V185 successor must scan raw current K lines and emit the complete monotonic chain:

`source_event_idx -> structure_confirm_idx -> poi_idx -> touch_idx -> reclaim_idx -> hold_confirm_idx -> signal_cutoff_idx -> planned_entry_idx`

It must not read historical trades/picks or any outcome fields. No `BUY_VALID` means successful empty-book operation, not a reason to relax gates.
