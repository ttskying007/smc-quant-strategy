# Current scanner anchor semantics and large-list paging

## Trigger

Use when a current SMC scanner exposes thousands of structural observation rows, or when displayed `Swing` and `Sweep` dates look mechanically uniform.

## Semantic audit before trusting a current funnel

A scanner that calculates:

```python
swing_idx = sweep_idx - RIGHT - 1
```

is not implementing “a prior confirmed swing may later be swept.” It admits only the fixed-offset case. This can make every displayed row share nearly identical dates and hide valid longer-lived liquidity anchors.

Correct it without threshold tuning:

1. Fix `response` to the latest completed bar and `sweep` to its preceding bar only for scanner-time materialization.
2. Enumerate every prior swing low whose right-side confirmation completed strictly before that sweep.
3. Exclude an anchor if any intervening bar from confirmation through the bar immediately before the sweep touched or penetrated that low: it is already consumed.
4. Retain anchors actually pierced by the sweep and reclaimed by its close.
5. If several qualify, use the nearest preceding anchor deterministically and emit: Swing date, confirm date, Sweep date, bar distance, canonical rule, and qualifying-anchor count.
6. A semantic change invalidates old seed/oracle/replay conclusions. Re-run outcome-blind seed generation → independent raw-bar Oracle → exactly one frozen strict-T+1 replay → independent audit → scanner-time comparison. Do not tune windows, thresholds, exits, years, or subsets after results are visible.

## Keep observation surfaces usable

Full per-symbol observability must not mean sending/rendering thousands of DOM rows in one dashboard response.

- Preserve total funnel counts and stage-specific summary lists when they are small.
- Paginate large observation lists **server-side**; client-side hiding still transmits and parses the full payload.
- Default to 100 rows/batch and offer bounded 50/100/200/500 sizes.
- Make `page`, `batch total`, and inclusive row range explicit; provide previous/next links.
- Apply the same page slice to the symbol list and its detailed table, so they cannot drift.
- Keep every partial row `RESEARCH_BLOCKED_NOT_EXECUTABLE`; pagination must never change admission, watchlist, position, or buy behavior.
- Verify page 1 and a later page have distinct row ranges, each response contains only the selected batch, response size falls materially versus the old full payload, and `/api/summary` plus `/api/picks` preserve the fail-closed contract.

## Minimal acceptance evidence

```text
semantic: swing_confirm < sweep < response < entry-eligible for every seed
oracle: generator identities == independent identities
replay: strict T+1 violations == 0
ui: page 1 and page 2 ranges differ; bounded rows/page
safety: buy_enabled=false and picks=[] if replay gate fails
```
