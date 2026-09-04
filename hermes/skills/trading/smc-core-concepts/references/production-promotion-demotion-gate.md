# SMC production promotion/demotion gate

Use this when a candidate engine/scanner appears to have strong headline metrics but audit finds pollution, or when deciding whether to write frontend/promoted artifacts.

## Non-negotiable production criteria

A version is production-usable only if all are true:

| Gate | Requirement |
|---|---|
| synthetic BE | `0` rows; no artificial breakeven/micro-win exit bucket used to inflate WR |
| micro profit cluster | no clustered tiny wins such as repeated `+0.5%` rows; micro_pct must be explicitly reported |
| T+1 | `0` same-day buy/sell violations |
| source purity | current watchlist/picks come from latest full-market scanner, not historical trade rows |
| scanner-time contract | current scanner dry-run reproduces the same semantic gates used by backtest/promotion |
| yearly coverage | minimum yearly sample must be stated; sparse years block promotion even with high WR |
| frontend/API sync | `/api/summary`, `/api/picks`, `/api/live-prices` must be verified after restart and checked for stale version rows |

## Promotion workflow

1. Audit headline metrics for synthetic exits and micro-profit clustering before trusting WR.
2. If polluted, demote the version immediately to historical diagnosis only; do not keep it as promoted while researching replacements.
3. Pick the next candidate only after losing-row review, excluded-bucket review, T+1 check, and scanner-time dry-run contract pass.
4. Only after the above pass, write the versioned production artifacts (`*_trades.json`, `*_picks.json`, `*_report.json`) and update frontend promoted contract.
5. Restart frontend/API service and verify concrete endpoints:
   - `/api/summary`: version/engine/trades/WR/avg_pnl match promoted version.
   - `/api/picks`: rows are live scanner/watchlist rows, not historical trades.
   - `/api/live-prices`: active rows have expected engine/status and no stale demoted-version rows.
6. Record a short decision report with: promoted/demoted state, why, metrics, endpoint proof, and what remains research-only.

## Demotion rules

Demote to historical diagnosis only when any of these are found:

- synthetic BE exits or artificial breakeven labels;
- repeated micro-profit bucket dominating wins;
- scanner-time dry-run fails semantic contract;
- candidate passes field contract only, but not candidate-generation contract;
- current picks are historical trades masquerading as current scanner output;
- yearly/monthly robustness fails despite good aggregate WR.

## Reporting format for Lei

Use a compact table with explicit `usable / unusable / research-only` status. Do not leave the system in an open-ended iteration state. If a version is not production-promoted, say exactly why and what gate failed. If production has been reverted to an older clean route, state the live endpoint proof.

## Session lesson: V152/V153/V164

- V152 headline WR was invalid because synthetic BE and micro `+0.5%` wins polluted the result; demote rather than maintain promoted status.
- V153 fixed pollution and became a candidate, but still required losing-row and excluded-bucket audit plus scanner-time contract before frontend write.
- V164 passed a corrected scanner dry-run contract, but remained research-only because dry-run verification is not the same as production promotion.
- Final acceptable state was: no V152 rows in `/api/summary`, `/api/picks`, `/api/live-prices`; live API routed to a clean non-V152 production contract.