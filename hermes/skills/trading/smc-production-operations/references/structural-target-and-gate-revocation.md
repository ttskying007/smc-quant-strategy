# Structural target validity and production-gate revocation

## Target validity at entry

For a reversal/absorption setup whose response bar confirms the event, a prior swing high can be used as a structural upside target only when it remains unconsumed at decision time:

```text
target > max(entry_open, response_bar_high)
```

Do not merely choose the nearest confirmed prior swing high above the prospective entry. If the completed response bar has already traded through that high, it is consumed liquidity, not a future target. Continue backward to the nearest confirmed prior high that remains above the response high; if none exists, reject the setup.

### Causal constraints

- The target pivot must be confirmed and visible before the sweep/event.
- The response bar is complete before the next-session entry decision.
- The chosen target must be above the response high and next open acceptance range.
- This is a semantic validity rule, not a post-outcome filter and not future leakage.

## Mandatory propagation test

When changing target semantics, update and rerun all of:

1. frozen replay target selection;
2. independent replay/audit implementation (separate code path);
3. current-epoch scanner materialization;
4. live order payload fields and UI/API target display;
5. promotion/release audit and any structural-RR feasibility gate.

Use a synthetic fixture with two visible highs: one consumed by the response bar and one still above it. Assert that the latter is chosen. Then consume every available target and assert the candidate is rejected.

## Gate failure must revoke executable state

A current candidate cannot remain executable after the frozen replay or independent audit loses its production gate. On a gate failure:

- mark every `PENDING_NEXT_OPEN` order as expired with a machine-readable gate-failure reason;
- set registry strategy to `null`, `buy_enabled=false`, and active-buy count to zero;
- preserve the current committed epoch and the exact failure reason for audit/UI;
- return a safe market-open no-op if no active strategy exists;
- scanner/release endpoints must emit explicit blocked artifacts with zero pending rows, rather than crashing or retaining stale scan output;
- `/api/summary`, `/api/picks`, and `/api/live-prices` must show fail-closed empty production state, never an old historical engine.

A passed execution job does not mean promotion is allowed. Production remains disabled until all frozen research gates pass again.
