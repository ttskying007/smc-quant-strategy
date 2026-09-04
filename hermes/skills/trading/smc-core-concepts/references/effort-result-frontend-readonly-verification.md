# Effort–Result Research Frontend: Read-Only Sync and Verification

## Scope

Use this when an outcome-blind / frozen-replay SMC ontology has passed research gates but must remain separate from production execution.

## Required presentation contract

The research page must show, from audit artifacts rather than historical active-pick files:

1. **Ontology and causal chain** — e.g. confirmed pre-existing swing → effort/reclaim → next-bar response → next-session eligibility.
2. **Frozen replay metrics** — total and yearly count, WR, AvgNet, PF, payoff, exit counts, strict T+1 violation count.
3. **Current scanner-time state** — epoch id/date, pending-next-open count, shadow decision, and explicitly `NO_BUY` when no exact current candidate exists.
4. **Gate evidence** — outcome-blind support, independent raw-bar oracle, frozen replay, independent metric parity, no historical fallback, no premature buy, T+1/serial checks.
5. **Trade-to-chart traceability** — each row links to a daily K-line that renders the causal nodes and the entry/exit record.

## Isolation rules

- `frontend_write=false` in a research audit does **not** mean the read-only research page is absent. It means no production/watchlist/position state was written.
- A diagnostic that intentionally adds no live behavior (for example, a post-freeze volume-strata or cost-stress audit) need not become a dashboard or selectable strategy. Keep it as an audit artifact unless the user explicitly asks for a research-table display.
- Never display historical replay rows as current picks. Empty current scanner data must render `EMPTY / NO_BUY`, not a fallback candidate.

## Verification sequence

1. Load the research page and read the populated state/metrics/gates from the rendered DOM.
2. Confirm current scanner and shadow state agrees with the newest release audit.
3. Open one known trade's K-line with the research version selected; verify the causal nodes occur in order and T+1 entry follows the response.
4. Confirm the dedicated API bundle exposes only audit/scanner/shadow/trade data and `buy_enabled=false`; it must not source production watchlist or positions.
5. Report separately: **research UI synchronization** versus **production release**. Do not infer the latter from the former.
