# EMPTY_BOOK: current epoch vs historical cutoff

Use when a dashboard appears to show a very old “last selection” date while production is intentionally fail-closed.

## Diagnostic contract

1. Query `/api/summary`, `/api/picks`, and `/api/live-prices` first. Record the registry authorization fields and the committed `dataDate` / epoch.
2. Read the current scanner-time artifact and scheduler observer log. A fresh epoch plus a zero-row scanner result that explicitly states `NO_PROMOTED_PRODUCTION_STRATEGY` or equivalent proves ingestion/scanner orchestration ran but deliberately made no candidate.
3. Treat `ops_latest.json` as archival in a revoked-strategy state. Its older generated date must not be surfaced as current scanner health or a current pick date.
4. Render `/monitor` in a browser. Its top production card must show the fresh market date and `当前最新选股日：无`; any historical date must be labelled as a frozen-research response/sample cutoff, not as a selection date.

## Interpretation

A current, committed market epoch with `production_strategy=null`, `buy_enabled=false`, `/api/picks=[]`, and a blocked no-write scanner is **not a stale scanner outage**. It is correct fail-closed behavior. The old date can still be a UX risk if visually prominent; keep the production state and historical cutoff in separate cards and state their non-equivalence in the historical card heading.

## Acceptance assertions

- Fresh committed epoch is visible in `/api/summary` and browser UI.
- Current picks are empty and buy authorization is false.
- Scanner metadata reports an explicit blocked/not-run reason rather than a stale historical run.
- Browser-visible historical cutoff includes `只读` and `非当前选股` (or equivalent).
- No historic artifact, frozen replay row, or old watchlist becomes a current candidate.
