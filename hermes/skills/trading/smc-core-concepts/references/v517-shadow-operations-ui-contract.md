# V517 Shadow Operations and UI Contract

## Scope

Use when production registry is `EMPTY_BOOK` while V517 Daily Effort–Result Absorption remains a research-promotable but shadow-only lineage.

## Non-negotiable separation

1. **Production surface**: current candidates, positions, and buy actions must be zero/disabled unless a separately promoted production strategy exists.
2. **Research surface**: V517 frozen replay, its full historical rows, yearly metrics, and K-line causal nodes remain visible read-only.
3. **Scanner surface**: only the newest committed daily-K epoch may produce `PENDING_NEXT_OPEN`; never backfill a current candidate from historical replay.
4. **Shadow surface**: only the immediately following committed epoch can validate the prior pending row's actual open. Rejected, missing, or late rows must remain no-action.

## Daily fail-closed sequence

Schedule only after the daily market data is expected to be final:

```text
refresh full-market daily K-line cache
→ require committed coverage epoch
→ validate prior epoch PENDING_NEXT_OPEN at this epoch's actual open (shadow only)
→ scan the newly committed epoch for new PENDING_NEXT_OPEN
→ run release/invariant audit
```

The observer may write audit artifacts only. It must not write production registry, watchlist, position ledger, trade ledger, or frontend active state.

## Frontend acceptance checklist

- K-line must preserve all visual signal toggles, all historical version choices, and daily/weekly/60m selectors even when `EMPTY_BOOK`; EMPTY_BOOK restricts writes, **not visual inspection**.
- Dashboard must separately display current production state and V517 research state.
- Historical research tables must label rows `REPLAY_ONLY` and offer explicit date filtering on `response_date`.
- Logs must render current committed epoch plus V517 seed/replay/scanner/release/shadow artifacts; do not present stale legacy V66/V90/V185 operations as current activity.
- `/api/picks` must remain empty and `/api/live-prices` must state no current position when no promoted strategy exists.

## Structural-target RR pitfall (V525)

A postulated pre-entry screen requiring the nearest already-visible swing-high target to provide `RR >= 1.5` must be treated as a separate hypothesis, not as a V517 parameter upgrade. On the frozen source run it reduced 404 seeds to 79 (year counts 16/35/19/9), failed the minimum-support gate (total >=300 and each year >=40), and had only 30.38% WR. Therefore it must not be promoted or used to replace the full-universe V517 contract.

## Verification

1. Compile server and adapter code.
2. Restart the UI and verify all pages plus `/api/summary`, `/api/picks`, `/api/live-prices`, `/api/effort-result`, and scheduler status return successfully.
3. Browser-check a V517 K-line with a replay trade and an ordinary symbol with zero V517 trades; both must retain visual SMC controls.
4. Verify date-filtering produces the expected strict subset of V517 historical replay rows.
5. Confirm the scheduled command has only the fail-closed observer and cron is active.