# Current-epoch pending lifecycle

## Purpose

Prevent two opposite temporal bugs in a next-open execution pipeline:

1. A later mutable research/release result retroactively erases a candidate that was authorized from the current committed epoch.
2. A candidate lacking a verified opening quote on its exact eligible session is filled at a later opening price.

## Required separation

```text
Historical replay trade: audit only; never a current candidate.
Current scanner row: response confirmed on the newest committed epoch.
Durable pending row: current scanner row plus decision-time execution authorization.
BUY_VALID/open position: only after exact-next-session fresh opening price passes the precommitted structural range.
```

A following-session execution is normal T+1 timing, not historical backfill.

## Durable row contract

Persist on each `PENDING_NEXT_OPEN` row:

- `data_epoch_id` and response date;
- expected exact next eligible session;
- structural stop and target fixed before entry;
- contract version and causal trace;
- authorization schema, strategy, `licensed=true`, license decision/time, immutable release artifact, and scanner epoch ID.

Require `authorization.scanner_epoch_id == data_epoch_id` before execution.

## State transitions

```text
licensed current scanner row
  -> PENDING_NEXT_OPEN

later aggregate/research gate fails
  -> freeze new admissions
  -> ADMISSION_FROZEN_PENDING_EXECUTION if signed pending rows exist
  -> do not change signed pending row identity/status

on expected session
  fresh quote has expected date and stop < open < target
    -> BUY_VALID
  fresh quote exists but outside range
    -> REJECTED_OPEN_OUTSIDE_STRUCTURAL_RANGE
  quote date stale/unavailable
    -> record NO_FRESH_EXCHANGE_QUOTE; retain only until the session ends

after expected session
  -> EXPIRED_MISSED_EXACT_NEXT_SESSION_OPEN
  -> never use a later opening quote
```

For an old controller that revoked a row before collecting any exact-session quote, use an explicit indeterminate legacy audit status. Do not infer a rejection, execution, or PnL from later data.

## Mutable-artifact and scheduling rule

`*_latest.json` is a mutable pointer. It cannot establish what was authorized when a row was created. The post-close order must be:

```text
committed refresh -> current scanner -> same-run release snapshot -> shadow validation -> durable pending write
```

The UI/API live-pending view must read the durable ledger, not the newest scanner/release pointer. Expose the source so a user can distinguish current ledger state from a current scanner report.

## Regression tests

Use isolated fixtures to assert all of:

1. A signed current pending row survives a later global gate failure, while new rows are not admitted.
2. That row can execute only on its exact expected session with a fresh quote and structural-range acceptance.
3. A later date expires the row before any quote lookup, preventing late fills.
4. The current API has no historical replay row in candidates/pending/positions.
5. Browser and direct API show the same pending count/source and never label pending as tradable or bought.
