# V152 demotion + V153/V164 scanner-contract lesson

## When this applies

Use this reference when a promoted SMC version has attractive headline WR/avg metrics but may be polluted by synthetic exits, micro-profit clustering, historical-completed-trade leakage, or a selector that cannot be reproduced at live scanner time.

## Session outcome

V152 was demoted from frontend/API production routing. V153/V164 were kept as audit/research artifacts only; no production, frontend, or watchlist write was allowed.

Final verified live state on `:8890`:

| Endpoint | Expected proof |
|---|---|
| `/api/summary` | `V102 / V102_BALANCED_VOLUME_GATE`, 195 trades, WR 87.7, avg 3.72, no V152 |
| `/api/picks/contract` | tradable `0`, watch-only `33`, raw `33`, `active_picks_not_historical_all_market=true` |
| `/api/picks` | 33 rows, engine `V90_DAILY_SCANNER_V88_CONTRACT`, no V152 |
| `/api/live-prices` | 5 watch-context rows, no V152 |

## Why V152 was not usable

V153 audit showed V152 headline metrics were polluted by synthetic breakeven and micro-profit clustering:

| Check | V152 |
|---|---:|
| trades | 127 |
| WR | 92.91% |
| avg pnl | 2.9407% |
| micro +0.5% rows | 40 |
| micro_pct | 31.50% |
| synthetic_be_n | 44 |
| synthetic_be_pct | 34.65% |

Do not preserve a promoted route when these symptoms appear, even if `/api/summary` looks good.

## V153 was historically clean but not live-scanner ready

V153 historical diagnostic result:

| Metric | V153 |
|---|---:|
| trades | 221 |
| WR | 83.26% |
| avg pnl | 3.3327% |
| synthetic_be_n | 0 |
| micro_pct | 0.90% |
| T+1 violations | 0 |
| min_year_n | 34 |

But V153 failed production promotion because the exact live scanner contract could not be reproduced:

- Failure reason: `EXACT_V153_SELECTOR_REQUIRES_v143_lifecycle_status_NOT_PRESENT_IN_SCANNER_DRY_RUN`
- Recent scanner rows: 2633
- `v143_lifecycle_status` missing rows: 2633

Rule: a clean historical selector is not enough. If it depends on delayed lifecycle/post-entry fields absent at scanner time, it is not a production selector.

## Loss/excluded bucket evidence

V153 losing rows:

| Exit reason | n |
|---|---:|
| `ZONE_CLOSE_DEAD_T1` | 29 |
| `STRUCTURE_SL_T1` | 4 |
| `TIME_STOP_21BARS` | 4 |

Excluded `CANCEL_AFTER_ENTRY_DAY_CLOSE` bucket:

| Metric | Value |
|---|---:|
| rows | 52 |
| WR | 67.31% |
| avg | 1.5757% |
| T+1 violations | 0 |

Interpretation: the excluded cancel bucket was not a T+1 or synthetic-BE issue; it was a weaker entry-day close-failure bucket. Exclusion improved quality historically but could not be used as an exact live scanner rule without delayed lifecycle observation.

## V164 corrected scanner dry-run

V164 proved a scanner-time corrected rule can remove obvious bad rows, but stayed dry-run only:

```text
(v132_true_takeover_2 OR v132_true_takeover_3_strict)
AND v132_reclaim_bull_body_pct <= 87.1077
```

Dry-run result:

| Check | Result |
|---|---:|
| source rows | 39,014 |
| recent45 rows | 2,348 |
| old V160 BUY recent45 | 1,462 |
| V164 corrected BUY recent45 | 333 |
| rejected from old V160 BUY | 1,154 |
| non-takeover BUY rows | 0 |
| body-fail BUY rows | 0 |
| outcome leak BUY rows | 0 |
| latest BUY date | 20260617 |
| latest BUY rows | 2 |

Rule: passing a corrected scanner dry-run proves only field/rule integrity. It does not prove full production promotion unless full-market backtest, lifecycle audit, T+1 audit, frontend routing, active-pick contract, and API smoke all pass.

## Operational checklist

Before promoting any V15x/V16x lifecycle/scanner candidate:

1. Audit headline WR for micro-profit and synthetic-BE pollution.
2. Verify T+1 violations are zero.
3. Separate historical diagnostic validity from live scanner reproducibility.
4. Require every production selector field to be available at scanner time; no post-entry lifecycle outcome fields.
5. If exact scanner contract fails, keep the version research-only; do not write production/frontend/watchlist artifacts.
6. Verify `:8890` endpoints after demotion/promotion and explicitly check `contains_v152=false` or equivalent stale-version absence.

## Artifacts from the session

- `/root/.hermes/smc_audit/v164_corrected_scanner_dry_run_20260622/final_closure_report.md`
- `/root/.hermes/smc_audit/v164_v153_pre_promotion_audit_20260622/report.md`
- `/root/.hermes/smc_audit/v164_v153_pre_promotion_audit_20260622/summary.json`
- `/root/.hermes/smc_audit/v164_corrected_scanner_dry_run_20260622/summary.json`
