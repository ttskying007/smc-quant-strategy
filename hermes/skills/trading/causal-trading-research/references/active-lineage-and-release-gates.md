# Active lineage and release-gate audit

## Trigger
Use before diagnosing a live trading dashboard or deciding whether a historical engine defect affects a current research/production surface.

## Rule: establish active lineage before analysis
Historical artifacts, fallback constants, and old engine files are not proof of the active strategy. First trace, with runtime evidence:

1. Service owner and actual process entrypoint.
2. Frontend route/adapter selected for the relevant page/API.
3. Production registry state and strategy/license fields.
4. Current scanner artifact and its source contract.
5. Whether the page is a research surface, a production surface, or an EMPTY_BOOK/fail-closed surface.

Report these separately:

```text
research/frontend ontology
production-license state
current scanner state
historical/audit-only artifacts
```

Do not attribute a current V517-style surface to an older V81/V85/V88-style engine merely because old routing constants or archived files remain in the codebase.

## Frozen replay release gates
An aggregate replay pass is insufficient. The replay gate and the release aggregator must both require, at minimum:

- total sample support;
- every declared year meets its minimum sample count;
- every declared year has positive average net outcome;
- monthly support across the complete observed interval;
- aggregate WR, AvgNet, PF, payoff requirements;
- zero strict T+1 violations.

The release aggregator must independently check yearly fields as defense against replay artifacts created before the annual-gate fields existed. Missing annual fields must fail closed.

## Frozen-object discipline
Adding a missing safety check is release-gate hardening, not permission to rerun, alter, or rescue a closed frozen ontology. Preserve the original replay artifact; run only the no-write release aggregation to prove that the strategy remains blocked. Never turn post-replay year, symbol, exit reason, RR, or feature slices into a new filter for that same frozen ontology.

## V517 example (audit-only)
A daily OHLCV effort-result chain can be semantically sound and Oracle-equal while still failing production: overall metrics may look positive while individual years have negative AvgNet and monthly support is sparse. The correct conclusion is fail-closed, not a return to older engines or an outcome-driven variant.
