# Fail-closed stale-pick-date and cron probe

## Use when

The dashboard appears to show that the most recent pick is far behind the current market date, especially after a research replay has been rejected and production is in `EMPTY_BOOK`.

## Diagnosis contract

Do not infer a failed scanner from an old date displayed in a historical/research table.

1. Query `/api/summary`, `/api/picks`, and `/api/live-prices`.
2. Read the authoritative production registry and current refresh epoch.
3. Assert all of the following separately:
   - committed market date equals the registry epoch date;
   - refresh gate passed and the epoch is `COMMITTED`;
   - `production_strategy is null`, `buy_enabled=false`, and `picks=[]` when fail-closed;
   - live scan metadata says `NOT_RUN_EMPTY_BOOK` with `NO_PROMOTED_PRODUCTION_STRATEGY`.
4. Open the actual `/monitor` page in a browser. It must label the old date as **historical replay response/signal date**, and independently show `当前最新选股日：无` plus the committed current market date.

A valid result is:

```text
fresh current data + intentional scanner skip + zero picks
!= stale scanner or missing data
```

Never revive an old watchlist or historical trade artifact merely to make the dashboard look current.

## Scheduler probe

A cron error such as `Permission denied` is an independent operational defect. It does not explain zero candidates if the production registry already blocks the scanner, but it still must be verified.

1. Check wrapper mode/owner and directory traversal with `stat` and `namei -l`.
2. Check the daemon's actual user and journal command record; do not assume the interactive shell and cron see identical permissions.
3. Invoke the wrapper once in a fail-closed state.
4. Require the controlled result `NOOP_FAIL_CLOSED_NO_ACTIVE_*STRATEGY` (or equivalent).
5. Hash production registry, positions, and pending orders before/after; they must not change.

This verifies the wrapper path without re-enabling strategy execution or mutating the production book.
