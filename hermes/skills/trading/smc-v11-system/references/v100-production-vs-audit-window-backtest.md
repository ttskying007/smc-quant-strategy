# V100 production-vs-audit window backtest pitfall

## Trigger
Use this reference when a user reports that a manual date-window backtest for V100/V88 frontend shows much worse WR/RR than `/api/summary` or the published production report.

## Durable lesson
`v100_trades.json` is an audit/full-tier artifact, not a production-only trade file. It can contain:

- `A_PRODUCTION_CORE` / `production_grade=A_PRODUCTION`
- `WEAK_ENV_WATCH_ONLY`
- `WATCH_ONLY_LOW_WR`
- `C_ROBUST_OBSERVE_ONLY`
- `REJECT_NOT_V98_A`

Production performance pages must filter to the active production contract before computing WR/RR:

```python
prod = [r for r in rows if r.get('v100_tier') == 'A_PRODUCTION_CORE' or r.get('production_grade') == 'A_PRODUCTION']
```

If the frontend directly windows over all rows in `v100_trades.json`, rejected/watch/weak-environment rows pollute production metrics and can make a good A-pool look like a sub-50% system.

## Required diagnostic sequence
1. Reproduce the user's date window exactly using `entry_date`.
2. Print both:
   - all-tier window metrics
   - A-production-only window metrics
3. Bucket the all-tier rows by `v100_tier`, `source_event`, `market_state`, `pd_zone`, `entry_mode`, and `exit_reason`.
4. Verify whether poor performance is caused by:
   - signal failure inside A pool, or
   - observation/reject tier pollution, or
   - TP/SL design failure, or
   - a stale/frontend routing issue.
5. Only after this split should you discuss SMC signal quality, TP/SL quality, or tuning.

## Frontend fix pattern
When V100 is served through the V88 frontend shell, filter V100 production rows in every route that computes production stats:

- cache refresh path (`_refresh_cache`)
- version-specific trade getter (`get_version_trades('V88')` when it prioritizes `V100_DIR/v100_trades.json`)
- any endpoint/page that bypasses the cache

Keep the full-tier artifact available for audit/diagnostics, but do not use it as the production trade universe.

## Reporting format for Lei
Report in tables:

- original all-tier metric vs corrected A-pool metric
- tier breakdown
- combo breakdown (`source_event + market_state + pd_zone`)
- corrected production rows
- explicit remaining gaps: e.g. missing multi-timeframe fields, unpromoted continuation system, or signal-specific TP/SL not yet separated.

Do not claim “SMC signal is bad” or “TP/SL is bad” from aggregate WR alone. First prove which tier/combination produced the bad window.
