# Fail-closed freshness and legacy-status isolation

## Trigger

Use when a dashboard in `FAIL_CLOSED_*` / `EMPTY_BOOK` appears to show an old "last pick", "last scan", or market date even though a newer committed market-data epoch exists.

## Failure mode

A UI often branches on the literal state `state == 'EMPTY_BOOK'`. A revoked registry may instead use a specific state such as `FAIL_CLOSED_REPLAY_GATE_FAILED` while still having:

```text
production_strategy = null
buy_enabled = false
active_buy_valid_count = 0
```

If the literal comparison fails, the UI can fall through to legacy `ops_latest`, retired scanner reports, or old scheduler state. This falsely presents a historical last-pick date as current scanner inactivity.

## Required diagnosis

1. Read the authoritative registry: strategy, buy flag, blocker, and embedded epoch.
2. Read the latest committed epoch manifest separately; compare its market date to all UI/API dates.
3. Inspect the actual live endpoint and browser-rendered label, not only source files.
4. Classify every older date as either current scanner metadata, legacy historical state, or an obsolete scheduler artifact.
5. Confirm whether the current scanner executed and was blocked, versus never ran.

## Correct routing contract

- Determine fail-closed production state from authorization fields (`production_strategy is None`; use `buy_enabled` for execution), not a literal state string.
- In fail-closed mode, expose the newest **COMMITTED** epoch as data freshness.
- Set scanner semantics explicitly, e.g. `NOT_RUN_EMPTY_BOOK` / `NO_PROMOTED_PRODUCTION_STRATEGY`, with blank scan date and scan timestamp when no licensed production scanner exists.
- Never use stale `ops_latest`, retired scanner reports, historical picks, or old scheduler timestamps to populate current candidate status.
- Keep legacy scheduler entries readable only as historical diagnostics; normalize stale `running=true` flags before reporting them.

## Minimal regression test

Fixture requirements:

```text
registry.state = FAIL_CLOSED_REPLAY_GATE_FAILED
registry.production_strategy = null
registry.buy_enabled = false
ops.data_date = old date
committed_epoch.market_date = newer date
```

Assert that the live/API metadata uses the committed date, scanner state is explicitly fail-closed, last scan fields are blank, current picks are empty, and buy authorization remains false. Then restart the real server and verify the browser label.
