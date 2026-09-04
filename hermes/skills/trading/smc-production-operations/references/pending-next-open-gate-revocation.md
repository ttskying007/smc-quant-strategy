# Pending-next-open versus executable production candidate

## Status vocabulary

Never call a raw scanner row “selected,” “tradable,” or “current pick” until it has passed every later state transition.

```text
current-epoch structural row
→ PENDING_NEXT_OPEN
→ fresh exact following-session opening quote
→ open strictly between pre-known stop and target
→ BUY_VALID
→ durable watchlist/position write
```

`PENDING_NEXT_OPEN` is a no-write, non-executable state. It may be shown as a research/live-setup observation only when the production license remains valid.

## Gate-revocation handling

A production controller must revoke every unfilled `PENDING_NEXT_OPEN` row when its research/replay/release gate fails after the row was created. Persist it as an immutable audit record, e.g. `EXPIRED_RESEARCH_GATE_FAILED`; never delete it, backfill it to a watchlist, or allow a later stale opening quote to execute it.

Distinguish three independent reasons a setup is not executable:

1. **No fresh opening quote** — retain pending only while its release gate remains valid; record the failed quote freshness attempt.
2. **Opening quote outside structural range** — reject permanently as `REJECTED_OPEN_OUTSIDE_STRUCTURAL_RANGE`.
3. **Release gate revoked** — expire permanently as `EXPIRED_RESEARCH_GATE_FAILED`, regardless of apparent chart quality.

## Reporting requirement

When a user asks why a prior “two stocks” disappeared, report the symbols and their complete lifecycle: response date, state at creation, expected execution date, each opening-quote attempt, revocation/rejection reason, closure timestamp, and whether any watchlist or buy write occurred. State explicitly if prior wording incorrectly conflated `PENDING_NEXT_OPEN` with `BUY_VALID`.

## Mutable latest-artifact pitfall

Do not treat a `*_latest.json` pointer as immutable proof of a past promotion. A later replay/audit can overwrite it and change a release decision. Production must retain a release snapshot/ID bound to each pending row; reports must compare the original release snapshot with the current release snapshot and explain the exact gate delta. Without that provenance, a status change is explainable only as a mutable-artifact transition, not as a market signal disappearing.
