# Shadow observer / production isolation contract

## Scope

Use when a research lineage has passed its frozen historical replay but has not independently earned permission to write production picks, positions, frontend state, or a trade ledger.

## Non-negotiable separation

A scheduled **shadow observer** may do only:

1. Refresh the data epoch and fail closed if it is not committed.
2. Evaluate the frozen next-open shadow contract.
3. Run current-epoch scanner dry-run and release audit.
4. Emit read-only audit output.

It must not call a production controller as a side effect. In particular, a successful research/release audit is not a production-write authorization.

## Audit procedure

Before enabling or retaining a scheduled observer:

1. Compile it (`python -m py_compile`).
2. Enumerate its subprocesses/AST call graph; verify there is no production controller, watchlist writer, position ingester, frontend writer, or historical-trade importer.
3. Inspect the production registry, pending-order file, and current scanner artifact. With zero current eligible rows, required result is `EMPTY_BOOK` / `NO_CURRENT_SIGNAL`, never a historical fallback.
4. Inspect all active SMC cron jobs. Pause legacy-lineage jobs that can create, push, or monitor picks outside the approved current shadow contract; retain only the specifically approved observer.
5. Re-run the shadow, scanner, and release-audit scripts. Require `production_write=false`, `watchlist_write=false`, `frontend_write=false`, zero BUY_VALID rows unless a new committed scanner row and its exact next-open epoch satisfy the separate release contract.

## Why this matters

A production controller can be technically fail-closed today because no row exists, yet remain a latent production-write path that activates silently when a later row appears. The safety property is therefore **absence of the call path**, not merely a zero-write result on one execution.

## Current application pattern

For the daily effort-result absorption lineage, preserve read-only shadow operation after its research replay passes. A separate Spring→Test→SOS ontology that fails its one frozen replay is closed and must not be revived through scanner routing or parameter variants.
