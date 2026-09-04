# V517-style causal scanner: production promotion and frontend closure

Use this pattern when a causal, current-raw-bar scanner has passed its declared research gates and is explicitly promoted to simulated/live production.

## Non-negotiable execution boundary

Do **not** turn replay rows or historical candidates into current buys. The only admissible path is:

```text
committed post-close epoch
→ current-date response scanner emits PENDING_NEXT_OPEN
→ durable pending snapshot
→ exact immediately-following session's opening price
→ require open > structural stop AND open < pre-known structural target
→ BUY_VALID / position
→ intraday SL/TP monitoring with A-share T+1 sell prohibition
```

If the exact next session is missed, reject/expire the pending row; never fill it later from cached bars.

## Deployment checklist

1. **Promote exactly one lineage in the production registry.** Set an explicit strategy identifier, `buy_enabled=true`, committed epoch identity, and row-level authorization invariants. Keep `historical_pick_fallback_disabled=true`.
2. **Quarantine old-lineage positions.** Do not mix a rejected/obsolete engine's open positions, ledger, or active picks into the newly promoted strategy's live UI/API.
3. **Write durable pending orders only after post-close scan and release audit.** A post-close job must refresh full-market K lines, require a committed coverage epoch, run scanner/release checks, then persist only current-epoch pending rows.
4. **Use the exchange-session opening price for entry validation.** Do not substitute a later last price for the open. Store the execution price, source, response date, data epoch, structural stop, structural target, swing/sweep/response indexes, and full causal trace.
5. **Carry provenance into the position.** Scanner output must include source bar indexes (`swing_idx`, `sweep_idx`, `response_idx`); map them to `zone_idx`/`conf_index` so the monitor classifies the position as auditable production rather than diagnostic-only.
6. **Install all three schedules, not merely monitoring:** post-close scanner/release/pending creation; exact-next-session morning entry validator; intraday monitor. Verify the service is active and inspect the installed cron entries.
7. **Synchronize all front-end surfaces.** Dashboard, selection/monitor page, `/api/picks`, live page, and K-line must show the promoted lineage only. The live page must not retain stale scanner metadata or positions from the old default engine.
8. **Restart and browser-verify the serving process.** A successful source edit is not deployment. Confirm the running page title/headings and APIs show the new production strategy.

## Regression tests

Use an isolated temporary monitor directory and a mocked quote:

- an in-range exact next-session open creates one `OPEN` position;
- position uses that opening price and preserves structural SL/TP;
- provenance indexes are present and position class is `PRODUCTION_CLEAN`;
- an SL event on the buy date does **not** close the position (T+1);
- a stale/missed next-open pending order expires rather than late-filling.

## Operational pitfall

System cron changes and process restarts can require separate authorization in the execution environment. Request that authorization before declaring deployment complete, then verify the actual service/process rather than assuming a source change or a cron-file write took effect.
