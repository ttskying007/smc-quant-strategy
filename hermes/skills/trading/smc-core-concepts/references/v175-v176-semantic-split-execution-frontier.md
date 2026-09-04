# V175/V176 Semantic Split + Execution Frontier Lesson

Use this reference when an SMC research loop has a profitable high-quality gate but semantic audits show the headline SMC label is overclaiming.

## What Happened

V172/V175 economics were good enough for production-style routing, but V174 showed the mass of profitable rows did **not** satisfy strict classical `SSL sweep -> CHOCH` ordering:

- `CLASSICAL_SWEEP_CHOCH_PASS`: 11 / 247 rows only.
- `NO_CLASSICAL_SSL_SWEEP`: 158 / 247 rows, and this was a strong profitable cluster.
- `NO_CLASSICAL_CHOCH`: 65 / 247 rows.
- `SEQUENCE_ORDER_FAIL`: 13 / 247 rows.

The right fix was not to force a classical sweep/CHOCH filter. The right fix was a semantic split:

- Primary production edge: `DEMAND_OB_TRUE_TAKEOVER_RECLAIM`.
- Preserve the old label as `original_event_type`.
- Keep `classical_structure_status` as an audited field.
- Set `classical_sweep_choch_claim = PASS` only for rows that truly pass the classical audit; otherwise `NOT_CLAIMED`.

## Required API / Frontend Closure

After semantic split materialization, verify operational closure separately from strategy closure:

- `/api/summary` must report the new version/engine.
- `/api/picks/contract` must separate tradable active, watch-only, and raw counts.
- `/api/picks` must have zero completed-trade pollution: no `exit_date`, stale `exit_reason`, realized `hold_bars`, or realized PnL aliases on active candidates.
- `/api/picks` must have zero old event overclaim (`event_type != SSL_SWEEP_CHOCH_REVERSAL`) while preserving `original_event_type`.
- `/api/live-prices` must keep semantic fields populated and watch-context rows non-tradable.
- Browser smoke must confirm visible version/semantic label and zero console JS errors.

Pitfall found in V175: active picks inherited `hold_bars`, `exit_date`, `exit_reason`, `mae_pct`, `mfe_pct`, and `rr_realized` from source rows. Fix in the materializer: for active candidate scope, clear realized outcome fields and explicitly set `pick_scope=ACTIVE_CANDIDATE`, `is_active_pick=True`, `pnl_pct=0`, `won=False`.

## Research Boundary After Semantic Closure

V176 loss frontier found no new production-grade scalar/category exclusion over V175. Remaining losses were mostly:

- `SL_DIRECT_ZONE_FAIL`: direct zone failure.
- `TIME_PARTIAL_FOLLOW_THROUGH_FAIL`: follow-through existed but did not reach TP.
- `TIME_GAVE_BACK_AFTER_NEAR_TP`: near-TP move gave back before time exit.

Do **not** continue adding scalar filters after this pattern unless they pass a full production gate. The better next direction is execution-layer收益释放:

- Reconstruct bar-level executable partial-profit / breakeven / trailing alternatives.
- Focus on TIME exits where MFE reached roughly `0.5R-1.2R` but did not convert to TP.
- Hard rule: do not improve WR by truncating winners; average PnL must not fall versus the base.
- Enforce T+1 in every replay.

## Usability Boundaries

Production candidate:

- `n >= 200`
- `min_year_n >= 35`
- `WR >= 84%`
- `AvgPnL >= 6.2%`
- `all_year_WR_min >= 82%`
- `micro_profit <= 1%`
- `T+1 violations = 0`
- Avg PnL must not decrease versus current production baseline.

Research-only candidate:

- `n >= 150`
- `min_year_n >= 25`
- `WR >= 85%`
- `AvgPnL >= 6.0%`
- `all_year_WR_min >= 83%`
- `T+1 violations = 0`

Unusable:

- Any T+1 violation.
- Any outcome leak in scanner/active candidate rows.
- Better WR with lower Avg PnL caused by cutting winners.
- Coverage below boundary.
- Overclaiming classical sweep/CHOCH when semantic audit does not prove it.
