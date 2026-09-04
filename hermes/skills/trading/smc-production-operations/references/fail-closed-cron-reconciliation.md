# Fail-closed strategy revocation: scheduler reconciliation

## Trigger
A frozen replay, independent metric audit, data-contract audit, or production gate revokes a strategy license (`FAIL_CLOSED`, `CLOSED_*`, `EMPTY_BOOK`).

## Mandatory closure sequence
1. Read the authoritative latest frozen decision and confirm registry authorization fields.
2. Enumerate scheduled jobs—not only scanner/API/UI state. Search by strategy, execution lineage, and legacy version names.
3. Read every candidate wrapper. Treat it as production-capable when it can invoke scanner materialization, pending-order persistence, exact-next-open execution, position monitoring, or a live controller.
4. Pause each job capable of advancing the revoked lineage. Retain source-health/cache-integrity monitors only when they cannot write candidates, positions, watchlists, or frontend production state.
5. Re-list scheduler state and record job IDs, pause state, and the closure reason in a no-write audit artifact.

## Pitfalls
- `shadow observer` is not evidence of read-only behavior. In the V517/V523 incident, `v523_post_close_shadow_observer.py` invoked `v526_v517_live_execution.py post-close`; it was therefore a production controller and needed pausing.
- Pausing only market-open execution is insufficient: post-close controllers can create pending orders, while position monitors can advance legacy state.
- An older historical pass cannot restore authorization after the latest frozen contract fails.
- `EMPTY_BOOK` is operational only when registry, scanner, API/UI, and every associated cron path agree.

## Minimal evidence package
- latest closure decision and failed gate;
- scheduler inventory before/after;
- subprocess call-chain evidence for misleading wrappers;
- remaining monitors proven source-only/no-write;
- resulting empty-book decision.
