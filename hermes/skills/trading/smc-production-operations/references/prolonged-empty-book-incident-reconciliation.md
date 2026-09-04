# Prolonged EMPTY_BOOK incident reconciliation

Use this when a user reports that the system has produced no selections or live trades for weeks/months.

## Evidence matrix

Collect four independent layers for the same date window:

| Layer | Required evidence | Interpretation |
|---|---|---|
| Refresh/epoch | committed epoch ID, market date, refresh return code, coverage gate | proves data-plane freshness only |
| Current scanner | fresh files, confirmed structure, sweep, reclaim, response break, full setup, partial-row next condition | proves current signal supply; never infer from historical trades |
| Release/admission | research/license result, failed checks, production strategy, buy flag, pending count | proves whether current rows may enter execution |
| Scheduler/execution | cron owner, per-run return code, scanner/release/controller state, positions, live checks | proves the chain actually ran and whether anything was executable |

## State normalization

Never collapse these into a generic “not run” message:

- `NO_CURRENT_SETUP`: scanner ran on the current committed epoch; full setup count is zero.
- `CURRENT_SETUP_BLOCKED`: current rows exist, but release/admission blocks them.
- `NO_LICENSED_STRATEGY`: registry has no authorized strategy or buy permission.
- `LIVE_READY_NO_CURRENT_SIGNAL`: an authorized strategy ran and found no executable current row.
- `FAIL_CLOSED_REFRESH_NOT_COMMITTED`: refresh rejected; this is a data-plane incident, not an ordinary empty book.

## Minimal reconciliation record

Persist a no-write JSON artifact with:

- incident date window;
- current committed epoch and market date;
- scanner funnel and representative partial rows with `furthest_stage`/`next_required`;
- release failed checks and production-license state;
- registry authorization fields;
- scheduler owner and every relevant return code;
- pending, position, and live-monitor counts;
- final root-cause classification.

## Interpretation rules

- Healthy refresh + zero full setups means current supply is zero; it does not prove scheduler failure.
- Nonzero current setups + blocked release means signal supply exists but is non-executable; do not erase it from diagnostics.
- No licensed strategy makes live execution a deliberate no-op; do not revive historical candidates to make the UI look active.
- A correct fail-closed state can still be a failed product objective when the user expects current selection and real-time trading. Report safety and availability separately.
- A research-frontier closure is not a production-operations diagnosis. If the user asks why they have had no picks/trades for a prolonged period, diagnose the production chain first.
