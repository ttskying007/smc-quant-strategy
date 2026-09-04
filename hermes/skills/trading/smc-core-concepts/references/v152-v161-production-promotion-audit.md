# V152→V161 production promotion audit lesson (2026-06-22)

Use this when an SMC candidate looks promoted in the frontend but later audits reveal metric pollution, scanner-contract gaps, or robustness failures.

## Key lesson

Do not treat a frontend `version` label or `/api/summary` success as final production validity. Separate four gates:

1. **Current frontend/API routing** — what `smc_unified.py` is actually serving.
2. **Backtest/release metrics** — n, WR, avg, loss, yearly coverage, T+1.
3. **Metric cleanliness** — no synthetic breakeven exits, no clustered micro-profit pseudo-wins.
4. **Scanner-time deployability** — current daily scanner can compute every selector field without outcome leakage.

A candidate can pass one gate and still fail another.

## V152 finding

Observed live/API state:

- `/api/summary` served `version=V152`, `engine=V152_HYBRID_LIFECYCLE_GATE`.
- `smc_unified.py:_promoted_contract_dir()` promoted V152 whenever `/root/.hermes/smc_opt_v152_hybrid_lifecycle_gate/v152_report.json` existed.
- `_promoted_trade_file()` used `v152_trades.json` when present.
- `/api/picks` returned 49 current context candidates; `/api/live-prices` returned 5 WATCH_ONLY_CONTEXT rows.

V152 headline metrics looked strong:

| metric | value |
|---|---:|
| n | 127 |
| WR | 92.91% |
| avg_pnl | 2.9407% |
| loss_rate | 7.09% |
| T+1 | 0 |

But V153 audit showed V152 was polluted:

| pollution check | V152 |
|---|---:|
| micro +0.5% rows | 40 |
| micro_pct | 31.5% |
| synthetic_be_n | 44 |
| synthetic_be_pct | 34.65% |
| min_year_n | 19 |

Conclusion: V152 can be online but should not be treated as a clean final production conclusion when synthetic BE exits or micro-profit clustering are present.

## V153 repair candidate

V153 repaired the V152 issue by dropping the weak `CANCEL_AFTER_ENTRY_DAY_CLOSE` bucket, restoring `PRE_BUY_GAP` coverage, and using original baseline exits only — no synthetic BE exits.

| metric | V138 baseline | V152 diagnostic | V153 repair |
|---|---:|---:|---:|
| n | 273 | 127 | 221 |
| WR | 80.22% | 92.91% | 83.26% |
| avg | 2.9981% | 2.9407% | 3.3327% |
| loss | 19.78% | 7.09% | 16.74% |
| micro_pct | 0.73% | 31.50% | 0.90% |
| synthetic_be_n | 0 | 44 | 0 |
| min_year_n | 41 | 19 | 34 |
| T+1 | 0 | 0 | 0 |

V153 release gate passed: `n>=200`, `min_year_n>=30`, `synthetic_be_zero`, `micro_pct<=1%`, `avg>=baseline`, `T+1=0`.

Promotion discipline: before wiring V153 to production, still run losing-row review, excluded-bucket attribution, and scanner-time dry-run contract for the exact V153 selector.

## V160/V161 lesson

V160 best rule:

- `TT2_CONFIRM_OR_CHASE_LE_3_5 + NONSTRICT_BODY_LE_86_6`
- n=225, WR=84.0%, avg=3.5105%, loss=16.0%, min_year_n=35, T+1=0
- release_pass=true but robust_pass=false
- bad_months_wr_lt60_n_ge3=1, weak_months_wr_lt78_n_ge3=8

Conclusion: V160 remains research-only despite release metrics because monthly robustness failed.

V161 dry-run scanner contract:

| scope | rows | ready | decision_available | outcome_leak |
|---|---:|---|---:|---:|
| all | 39013 | False | 39001 | 0 |
| recent45 | 2633 | True | 2633 | 0 |
| v160_buy_recent45 | 1726 | True | 1726 | 0 |

V161 proves scanner-time field availability and no outcome leakage for recent/current rows. It does **not** override V160 stability failure and does **not** promote V160 to production.

## Procedure for future SMC promotion audits

1. Hit live APIs and record actual routing: `/api/summary`, `/api/picks`, `/api/live-prices`.
2. Trace `smc_unified.py` routing helpers: `_promoted_contract_dir()`, `_promoted_trade_file()`, `reload_metrics()`, pick-source loaders.
3. Read the promoted report JSON; capture production_write, live candidate write status, n/WR/avg/loss/T+1, by-year split.
4. Run or inspect metric-cleanliness audit: micro-profit clustering, synthetic BE exits, min yearly coverage.
5. Run scanner-time dry-run contract against real daily scanner rows, not historical chosen rows.
6. Keep conclusions separated:
   - **online/routed**
   - **metric-pass**
   - **metric-clean**
   - **scanner-contract-clean**
   - **robust/stable**
   - **production-promotable**
7. If any gate fails, say exactly which gate failed and do not call the candidate production-ready.

## User-facing conclusion style

For Lei, report this class of result as tables with clear field names. Explicitly state online state, valid state, and next action. Do not bury the blocker in prose; use a direct line such as:

> V152 is online, but V153 audit proves V152 has synthetic BE pseudo-win pollution; V160/V161 are research/contract artifacts only; next promotable path is V153 after scanner-time contract + losing-bucket audit.
