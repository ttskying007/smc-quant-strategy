# V79/V80 Full-Candidate Production Gate Lesson

Use this reference when an SMC candidate version looks strong on a selected subset but coverage is thin, especially after V74/V75/V76/V77/V78-style layered filtering.

## Durable lesson

Do **not** promote a gate that was only validated on an already-selected subset. A narrow gate can look excellent while simply inheriting the parent subset's blind spots. Push the rule back into the full candidate generation layer and recompute every derived field there.

## What happened

V78 passed quality checks on the V74/V75 selected layer but had only 106 trades and only 2 trades in 2024. Replaying V78 from the full V71/V74 annotated universe showed the problem was structural: the exact V78 gate still produced only 110 trades after full-layer recomputation.

| Version | Validation layer | Trades | WR | Avg PnL | SL rate | Decision |
|---|---|---:|---:|---:|---:|---|
| V78 | V74/V75/V77 selected subset | 106 | 72.64% env-exit | +1.7660% | 7.55% | Not production: 2024 coverage = 2 |
| V79 | Full V71/V74 candidate replay of V78 rules | 110 | 71.82% env-exit | +1.7108% | 7.27% | Not production: total/2024/2026 coverage fail |
| V80 | Full candidate production gate | 1109 | 67.18% env-exit | +1.2132% | 19.75% | Production gate passed |

## V80 gate that restored coverage

Use the full V71/V74 annotated candidate layer, not V75/V77 selected files. Recompute V76/V77 fields on that full layer, then gate with:

1. Broad environment is demand-valid: `ACCUMULATION / RECOVERY / BULL_CONTINUATION`.
2. Context/Event/POI story is valid:
   - `UP_CONTINUATION_BOS_POI_RECLAIM`
   - `DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM`
   - `BULL_TRANSITION_POI_RECLAIM`
3. Prior 10 sessions contain at least 3 demand-valid environment days.
4. If story is `DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM` and market state is `RECOVERY`, require `v77_recovery_quality == TRUE_RECOVERY_DEMAND_VALID`.
5. Keep T+1-safe environment exit: after entry day, exit on `DISTRIBUTION` or `BEAR_RISK` before the original exit.

## V80 full validation

| Year | Trades | WR | Avg PnL | SL rate | Env exit rate | Cum |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 66 | 72.73% | +1.5147% | 18.18% | 10.61% | +99.97% |
| 2024 | 89 | 66.29% | +1.4979% | 13.48% | 26.97% | +133.31% |
| 2025 | 707 | 67.47% | +1.2599% | 17.26% | 25.60% | +890.72% |
| 2026 | 246 | 65.04% | +0.8889% | 29.67% | 6.50% | +218.68% |

Audits:
- T+1 violations: 0 / 1109.
- Field audit for frontend contract: `entry_date`, `select/pick_date`, `join_date`, `zone`, `cost_line`, `volatility_pct` all 0 missing.

## Implementation files

- `/root/.hermes/scripts/v25/v79_full_candidate_v78_replay.py`
- `/root/.hermes/scripts/v25/v80_full_candidate_production_gate.py`
- `/root/.hermes/smc_opt_v79_full_candidate_v78_replay/v79_report.json`
- `/root/.hermes/smc_opt_v80_full_candidate_production_gate/v80_report.json`
- `/root/.hermes/smc_opt_v80_full_candidate_production_gate/v80_trades.json`
- `/root/.hermes/smc_opt_v80_full_candidate_production_gate/v80_picks.json`

## Frontend integration notes

When promoting a new production version in `smc_unified.py`, update all three places:

1. `ACTIVE_VERSION` preference chain.
2. `ACTIVE_TRADE_FILE` / `ACTIVE_PICK_FILE` mapping.
3. `get_version_trades()` / `get_version_picks()` explicit version loaders.

Also add the new version to `current_scoped_versions` if picks are active/watchlist-like and should not be filtered as historical backtest representatives.

## Pitfalls

- Do not use historical trades as current picks unless the pick scope is explicit and the frontend contract is satisfied.
- Do not leave V68/V66/V78 as production if their signal definition or coverage failed; production promotion requires full-layer validation and frontend/API zero-missing-field checks.
- If a patch tool call would be very large, split it into smaller targeted patches; do not retry the same large patch content.
