# V307 Industry Leadership Transmission Audit

## Trigger
V306 showed opening gap source is highly informative: `INDUSTRY_GAP_LED` had 1,462 rows / WR 63.27% / Avg +3.84, but only covered 202605-202606. V307 tests whether the real mechanism is not just gap source, but **industry leadership transmission** during entry-day first120 15m window.

## Scope
- Script: `/root/.hermes/scripts/v25/v307_industry_leadership_transmission_audit.py`
- Result: `/root/.hermes/smc_audit/v307_industry_leadership_transmission_latest.json`
- Source: V306 rows
- Rows: 87,499
- Symbols: 4,154
- K15 files: 4,653
- Stock-date 15m features: 223,005
- Industry-date features: 3,330
- T+1 violations: 0
- No production/frontend/watchlist writes.

## Method
For every entry date, scan all local 15m cache files and compute first120 industry leadership:

- stock first120 ret / drawdown / push / amount
- industry first120 median ret
- industry first120 up percentage
- industry first120 hot percentage
- industry first120 amount
- industry rank by ret / up / amount among all industries for that date

Candidate-level labels:

| Label | Meaning |
|---|---|
| `industry_leader_state` | `LEADER_TOP20`, `LEADER_TOP40`, `NON_LEADER` based on first120 industry ret/up ranks |
| `candidate_participation` | candidate first120 ret >= 0 and drawdown > -1.5% |
| `leader_transmission` | industry leader state + candidate participation |

Then combine with V306 `gap_source`, risk, accumulation and sweep buckets.

## Results
Baseline after leadership feature coverage:

| Scope | N | WR | Avg | SL | GAP_SL | Months |
|---|---:|---:|---:|---:|---:|---|
| covered V306 rows | 87,499 | 39.62% | -0.69% | 51.71% | 4.42% | 202604-202607 |

High-quality pockets:

| Combo | N | WR | Avg | SL | Month WR |
|---|---:|---:|---:|---:|---|
| `LEADER_TOP20 + INDUSTRY_GAP_LED + m120_iup>=65` | 407 | 73.96% | +6.08% | 19.41% | 202605 69.52 / 202606 77.73 |
| `industry ret rank TOP20 + INDUSTRY_GAP_LED + candidate PARTICIPATE` | 639 | 73.40% | +5.66% | 24.10% | 202605 68.02 / 202606 79.66 |
| `LEADER_TOP20 + PARTICIPATE + INDUSTRY_GAP_LED` | 655 | 71.60% | +5.37% | 24.12% | 202605 65.73 / 202606 78.60 |
| `TOP20 industry up rank + INDUSTRY_GAP_LED + RISK5_8` | 235 | 76.17% | +4.16% | 23.83% | 202605 65.45 / 202606 85.60 |

## Interpretation
V307 confirms V306's mechanism: the strongest branch is **industry-led opening gap + industry top20 first120 leadership + candidate participation**. This is meaningfully better than generic market strength, simple morning persistence, or per-stock DNA.

However, the strong pockets still concentrate in 202605/202606. This is a coverage limitation of the available 15m data and V302/V305 near-term candidate pool; it is not enough for production promotion.

## Closure
Do not keep tuning per-stock DNA, first60/first120, or generic gap buckets. The next useful direction is:

`Industry Leadership Transmission → Candidate industry rank → Candidate participation → Same-source POI lifecycle → executable entry`

Before production, one of the following is required:

1. extend 15m history beyond current near-term cache and rerun V307 across a longer period; or
2. build a scanner-time live industry leadership module and shadow it without production writes; or
3. find daily/proxy features that reproduce the first120 industry leadership signal across full 2023-2026 history.

## Verification
Focused ad-hoc verifier passed:
- compile/import + bucket boundaries
- metrics fixture
- no-write artifact contract
- source-row count recomputation
- T+1=0
- baseline recomputation
- selector field safety

Verifier output: `status=PASS`, rows=87,499, symbols=4,154, T+1=0.
