# V301 previous-day board leadership overlay

Date: 2026-07-03
Mode: no-write research audit. No production/frontend/watchlist writes.

## Hypothesis

After V300 showed entry-session 60m price/volume diffusion is informative but still monthly-unstable, test a different parent-state source available before entry: previous trading day's market/industry limit-up and strong-board leadership.

## Source

- Script: `/root/.hermes/scripts/v25/v301_prevday_board_leadership_overlay.py`
- Summary: `/root/.hermes/smc_audit/v301_prevday_board_leadership_latest.json`
- Enriched rows: `/root/.hermes/smc_audit/v301_prevday_board_leadership_no_write_20260703_160536/v301_enriched_rows.csv`
- Two-year guard: `/root/.hermes/smc_audit/v301_prevday_board_leadership_no_write_20260703_160536/v301_two_year_stability_probe.json`

## Method

1. Start from V300 enriched executable 60m rows: 137,551 candidate executions.
2. Build daily board context from all local `*_daily_750.json` files using only previous trading day values.
3. For each candidate, join previous-day:
   - market limit-touch count / limit-close count / strong 3% and 5% participation;
   - industry limit-touch count / limit-close count / strong 3% and 5% participation;
   - industry board rank and industry-vs-market strong participation lead.
4. Test board leadership grids on both raw V300 executable rows and V300's two-year stable base.
5. Re-rank with a two-year guard requiring both 2025 and 2026 coverage, month coverage, and T+1=0.

Selectors use only prior trading day board fields plus entry-time V300 fields. They do not use `pnl`, `reason`, exit labels, MFE/MAE, or any post-entry outcome field.

## Results

Raw V300 enriched baseline:

| N | WR | Avg | 2025 WR | 2026 WR | weakest month | T+1 |
|---:|---:|---:|---:|---:|---:|---:|
| 137,551 | 48.55% | +0.55% | 57.23% | 45.91% | 26.88% | 0 |

V300 two-year base before board overlay:

| N | WR | Avg | 2025 WR | 2026 WR | weakest month | T+1 |
|---:|---:|---:|---:|---:|---:|---:|
| 3,935 | 53.04% | +1.44% | 58.50% | 51.36% | 37.28% | 0 |

Best apparent board pocket without year guard:

| Rule | N | WR | Avg | Year coverage | Min month WR | T+1 |
|---|---:|---:|---:|---|---:|---:|
| `raw_enriched + mkt_strong5>=20 + industry limit_touch>=3 + industry strong5>=20` | 6,541 | 73.72% | +5.36% | 2026 only | 43.91% | 0 |

Two-year guarded best:

| Rule | N | WR | Avg | 2025 WR | 2026 WR | Min month WR | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V300 two-year base + no board filter | 3,935 | 53.04% | +1.44% | 58.50% | 51.36% | 37.28% | 0 |

## Interpretation

- Previous-day board leadership has strong recent/2026 information: a hot prior board plus strong industry can produce high 2026 WR pockets.
- But once a two-year guard is applied, board leadership contributes no additional stable filter over V300's existing two-year base.
- The best two-year result is literally the V300 base with no board filter. All prior-day board constraints either fail to improve weak-month stability or reduce coverage.
- Therefore, previous-day limit-up/strong-board leadership is a useful diagnostic state label, not a production-closed parent router.

## Decision

Do not promote V301. Do not continue tuning previous-day daily board/limit-up thresholds.

The repeated closure from V297-V301 is now clear:

- same-source 60m lifecycle is better than daily zone back-checking, but still weak-month unstable;
- entry-session 60m market/industry volume diffusion helps but not enough;
- previous-day board leadership does not solve stability under two-year guard.

Next viable branch requires genuinely more causal intraday evidence: 15m sequence, opening auction / first-15m amount persistence, true sector-leading order flow, or refreshed longer 60m/15m data. Without new data, stop the 60m/daily-board threshold branch.

## Verification

Focused ad-hoc verification required for this script:

- py_compile/import;
- no-write/source contract;
- source row count recomputation;
- T+1 violations = 0;
- selector fields are prior-day or entry-time only, with no outcome leakage.
