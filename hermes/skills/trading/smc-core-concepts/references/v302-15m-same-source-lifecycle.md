# V302 15m same-source lifecycle audit

Date: 2026-07-03
Mode: no-write research audit. No production/frontend/watchlist writes.

## Hypothesis

After V297-V301 closed the 60m/daily-board threshold branch, test whether a more granular 15m same-source lifecycle (`ACC compression -> downside MAN sweep -> bullish reclaim -> DIS/takeover -> next daily open`) can produce cleaner A-share SMC candidates.

## Source

- Script: `/root/.hermes/scripts/v25/v302_15m_same_source_lifecycle_audit.py`
- Summary: `/root/.hermes/smc_audit/v302_15m_same_source_lifecycle_latest.json`
- Rows: `/root/.hermes/smc_audit/v302_15m_same_source_lifecycle_no_write_20260703_202220/v302_rows.csv`
- Cache: `/root/.hermes/kline_cache_15min/*_15min_800.json`

## Method

1. Enumerate all local daily-cache symbols (`*_daily_750.json`).
2. Fetch/reuse Tencent `m15` bars, requesting 800 bars per stock.
3. Normalize to `{t,d,o,h,l,c,v}` local cache.
4. For every stock, scan same-source 15m lifecycle:
   - 8/12/16-bar accumulation range;
   - quiet volume vs previous window;
   - downside sweep below ACC low;
   - bullish reclaim back above ACC low;
   - takeover close above ACC high and reclaim high;
   - next trading day open entry;
   - daily T+1 replay, exits only from the day after entry.
5. Mine simple entry-time buckets only: ACC width, sweep depth, risk, impulse, volume quietness.

Selectors do not use `pnl`, `reason`, MFE/MAE, hit flags, or post-entry fields. Cache/audit writes only; no production route changed.

## Results

| Metric | Value |
|---|---:|
| Symbols total | 4,655 |
| 15m covered | 4,653 |
| 15m median rows | 800 |
| Candidate rows | 67,559 |
| Candidate symbols | 4,591 |
| Year coverage | 2026 only |
| Month coverage | 202602-202607 |
| Base WR | 39.38% |
| Base Avg | -0.645% |
| SL | 44.32% |
| GAP_SL | 15.05% |
| T+1 violations | 0 |

Best mined pockets were not production-grade:

| Variant | N | WR | Avg | Weakest month |
|---|---:|---:|---:|---:|
| `ACC_VWIDE>=5 + SWEEP1.2_2.5 + RISK3_5` | 56 | 58.93% | +0.85% | 0.00% |
| `ACC_TIGHT<1.5 + SWEEP>=2.5 + RISK5_8` | 86 | 54.65% | +0.94% | 0.00% |
| `ACC_VWIDE>=5 + SWEEP>=2.5 + RISK>=8` | 211 | 53.55% | +1.98% | 0.00% |
| `ACC_VWIDE>=5 + SWEEP<0.6 + RISK>=8` | 1,142 | 52.54% | +1.44% | 36.86% |
| `ACC_VWIDE>=5 + RISK>=8` | 2,515 | 51.49% | +1.14% | 34.21% |

## Interpretation

15m granularity gave massive supply (67,559 rows from only recent 2026 cache), but the naive same-source ACC/MAN/DIS grammar is worse than the 60m branch:

- base WR is only 39.38%, Avg negative;
- high-WR pockets are tiny and month-unstable;
- large pockets remain around 51-53% WR with weak-month WR in the 30s;
- GAP_SL is high at 15.05%, meaning many 15m takeovers fail before the next-day executable entry.

This disproves the simplest assumption that “15m is better just because it is finer.” The useful issue is not timeframe granularity alone. The current 15m pattern still generates many fake micro takeovers that do not survive to A-share T+1 execution.

## Decision

Do not promote V302. Do not continue tuning the naive 15m ACC/MAN/DIS thresholds.

The next branch must test **executable intraday entry timing**, not just finer signal generation followed by next-day open:

- first/second 15m after entry-day open hold/continuation;
- auction/opening gap quality;
- same-day intraday persistence before buy while still enforcing T+1 exits;
- sector/market synchronized 15m expansion at the actual executable buy window.

Without executable timing confirmation, same-source 15m POI generation alone does not solve production stability.

## Verification

Focused ad-hoc verification PASS:

- py_compile/import and helper boundary checks;
- summary no-write contract;
- source row count recomputation: 67,559 rows / 4,591 symbols;
- T+1 violations = 0;
- row fields checked for obvious outcome-leak names;
- 15m cache normalized contract checked.
