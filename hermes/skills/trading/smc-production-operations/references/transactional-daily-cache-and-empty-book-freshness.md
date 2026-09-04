# Transactional daily-cache refresh and EMPTY_BOOK freshness

## Problem class

A daily cache refresh may receive a full 750-bar series for SH/SZ but only a single current-day bar for some BJ symbols. The last bar may change between late snapshots and the official close. Separately, a production registry can be intentionally fail-closed while its stored data epoch is older than the committed market-data epoch.

## Safe cache rule

1. Stage every symbol and evaluate coverage before promotion. A failed refresh must leave the prior committed manifest and cache intact.
2. A partial Tencent response must never replace a full cache.
3. For a partial response, permit replacement only of the existing cache's **latest date**; require strict OHLC alignment for every older overlapping date.
4. Merge by date, preserving history and replacing at most that tail bar. A mismatch on any historical overlap rejects the symbol.
5. Treat provider open-status as an exclusion witness when available. If the endpoint has no market-status field, apply the normal completed-session cutoff; record that this is time-based rather than provider-confirmed.
6. Verify both a synthetic fixture (tail update allowed; historical mismatch rejected) and a real staged sample before a full refresh.
7. Do not reject a genuinely new listing merely because 750 bars are impossible. A short daily history is acceptable only when it has at least 20 strictly increasing, unique daily dates and its first date is within approximately one year. Mark it explicitly as short-listing history. Reject one/few-row provider truncations, stale short series, duplicates, and disorder.

## EMPTY_BOOK dashboard rule

`EMPTY_BOOK` communicates strategy/license status, not data staleness. The UI/API should:

- keep `production_state`, `buy_enabled=false`, and zero active candidates from the production registry;
- expose `data_status` from the latest **committed** market-data manifest when one exists;
- fall back to registry-embedded epoch only if no committed manifest is readable;
- never treat fresh cache data as authorization to create candidates or buy.

## Acceptance checks

- Full refresh passes request and current-date coverage gates and writes a new committed epoch.
- A rejected subsequent refresh cannot replace the committed epoch.
- Cache-date count is reported against the request denominator, not only files currently cached.
- `/api/summary` shows the committed epoch while remaining `EMPTY_BOOK`; `/api/picks` is empty and `/api/live-prices` has no `BUY_VALID` rows.
- Restart the serving process and verify the browser dashboard semantics after the API checks.
