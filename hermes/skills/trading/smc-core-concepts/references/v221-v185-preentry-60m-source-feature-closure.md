# V221 V185 pre-entry 60m source-feature closure

Date: 2026-06-27

## Trigger
Use after V220 when considering whether Baostock 60m data can improve V185 by filtering low-WR rows using only information available **before** daily entry.

## Artifact
- Script: `/tmp/v221_preentry_60m_source_filter.py` (temporary research script, no production writes)
- Output: `/root/.hermes/smc_audit/v221_v185_preentry_60m_feature_audit_20260627_024936/`
- Source: `/root/.hermes/smc_opt_v185_combined_production_candidate/v185_trades.json`
- Cache: `/root/.hermes/smc_audit/baostock_60m_cache_v221_preentry/`

## No-leak contract
- Features use Baostock 60m bars strictly before `entry_date` (`end_date = entry_date - 1 day`).
- No entry-day intraday bars, no exit path, no outcome fields in selectors.
- Evaluation uses realized V185 outcomes only after selecting.
- No production/frontend/watchlist writes.

## Gate used
Post-V185 production improvement requires:
- `n >= 300`, `min_year_n >= 40`
- `WR >= 87%`, `AvgPnL >= 6.8%`
- `all_year_WR_min >= 84%`, `micro_profit_pct <= 1%`
- T+1 violations = 0

Research-only usable requires:
- `n >= 260`, `min_year_n >= 35`
- `WR >= 88%`, `AvgPnL >= 6.8%`
- `all_year_WR_min >= 84%`, `micro_profit_pct <= 1%`
- T+1 violations = 0

## Result
Decision: `V221_PREENTRY_60M_SOURCE_FEATURE_AUDIT_NO_GATE_PASS__NO_WRITE`.

Fetch coverage: `334/334` V185 rows.

Baseline V185:
| n | WR | AvgPnL | minYear | yearWRmin | micro | T+1 |
|---:|---:|---:|---:|---:|---:|---:|
| 334 | 86.23% | 6.5628% | 41 | 82.81% | 0.90% | 0 |

Source split confirms the weak component remains V175:
| bucket | n | WR | AvgPnL | minYear | yearWRmin | micro | loss_n |
|---|---:|---:|---:|---:|---:|---:|---:|
| V175_BASELINE | 247 | 83.81% | 6.0493% | 38 | 81.71% | 1.21% | 40 |
| V185_CHILD | 87 | 93.10% | 8.0206% | 3 | 82.35% | 0.00% | 6 |

## Low-WR / loss signatures
Losers show stronger prior-day intraday chase/exhaustion but not enough stable coverage to gate production:
- ALL: prior-day close-position losers `80.54` vs winners `75.24`; previous close vs zone-high losers `2.72%` vs winners `2.21%`; prior-day volume ratio losers `1.41` vs winners `1.27`; risk losers `6.62%` vs winners `5.98%`.
- V175 only: prior-day close-position losers `80.98` vs winners `74.97`; risk losers `6.77%` vs winners `6.55%`.
- V185 child: losses are few (`6`) but show high prior-day volume ratio (`2.16` vs `1.30`) and higher risk (`5.61%` vs `4.52%`).

Interpretation: 60m pre-entry data confirms a real exhaustion/chase pattern, but it is a weak classifier and mostly identifies small high-quality pockets rather than a stable production-width engine.

## Best pockets and why rejected
Top pockets after keeping all V185 child rows and filtering only V175 rows:
- `V175.v132_reclaim_body_range_pct<=41.7678`: `n=112`, WR `93.75%`, Avg `7.5673%`, yearWRmin `85.0%`, micro `0.89%`, but minYear `7`.
- `V175.risk_pct<=4.38744`: `n=112`, WR `93.75%`, Avg `7.4539%`, micro `0`, but minYear `5`.
- 60m-only pocket `V175.pre60m_prevday_close_above_zone_high==0`: `n=91`, WR `93.41%`, Avg `7.8612%`, micro `0`, but minYear `3`.
- Best wider pair `pre60m_prevday_close_pos_pct<=85.9289 AND pre60m_prevday_range_pct>=4.56415`: `n=206`, WR `92.23%`, Avg `7.7463%`, yearWRmin `89.47%`, micro `0.49%`, but `n/minYear` below research gate (`206/17`).

No production or research gate passed (`pass_count=0`).

## Decision / next direction
Close pre-entry 60m scalar filtering as a production-upgrade path. It provides diagnostic evidence but collapses sample/year coverage.

Do not keep iterating thresholds on V185/V175 rows. Remaining valid directions:
1. genuine new candidate generator with pre-entry intraday semantics, not row filtering;
2. industry/sector participation layer if a non-leaking sector data source is available;
3. V185 production stabilization/live guard/cron if no new data layer is available.
