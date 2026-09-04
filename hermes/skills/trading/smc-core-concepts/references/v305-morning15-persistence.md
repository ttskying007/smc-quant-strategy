# V305 morning 15m persistence audit

Date: 2026-07-04
Mode: no-write research audit. No production/frontend/watchlist writes.

## Hypothesis

V303/V304 proved first/second 15m executable confirmation and same-window market/industry diffusion only produce small fragile pockets. V305 tests the next concrete branch: whether **longer executable morning persistence** can filter fake 15m lifecycle takeovers.

Instead of buying at the open or after the first/second 15m bar, V305 waits for:

- first 60m hold/takeover, entry at the next 15m bar open;
- first 120m morning persistence/no-fade, entry at the next 15m bar open;
- same-window market/industry/stock amount diffusion computed only from already-observed first60/first120 bars.

This is still no-write research and preserves strict A-share T+1 exit replay.

## Source

- Script: `/root/.hermes/scripts/v25/v305_morning15_persistence_audit.py`
- Summary: `/root/.hermes/smc_audit/v305_morning15_persistence_latest.json`
- Rows: `/root/.hermes/smc_audit/v305_morning15_persistence_no_write_20260704_045423/v305_rows.csv`
- Input: V302 rows `/root/.hermes/smc_audit/v302_15m_same_source_lifecycle_no_write_20260703_202220/v302_rows.csv`
- Industry map: `/root/.hermes/smc_audit/v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json`

## Method

For each V302 same-source 15m lifecycle candidate:

| Mode | Entry semantics |
|---|---|
| `MORNING60_HOLD` | first4 15m bars hold above SL/ACC low and close above day open; buy next 15m open |
| `MORNING60_TAKEOVER` | first4 bars hold ACC low and close above ACC high; buy next 15m open |
| `MORNING120_PERSIST` | first8 bars hold ACC zone and close above ACC high/day open; buy next 15m open |
| `MORNING120_NO_FADE` | first8 bars do not fade first60 and close above day open; buy next 15m open |

For the corresponding first60/first120 window, compute:

- market up percentage / median return;
- industry up percentage / median return;
- industry amount ratio;
- stock amount ratio vs previous 5 sessions;
- stock relative return vs industry median.

All features are available before the simulated intraday entry. Exit replay starts from the next daily bar, so same-day buy/sell violations must remain 0.

## Results

Coverage:

| Metric | Value |
|---|---:|
| V302 rows | 67,559 |
| V305 executable rows | 88,351 |
| Symbols | 4,197 |
| Needed entry dates | 75 |
| 15m files | 4,653 |
| Market feature keys | 446,444 |
| T+1 violations | 0 |

Baseline:

| Scope | N | WR | Avg | SL% | GAP_SL% | Weakest month WR |
|---|---:|---:|---:|---:|---:|---:|
| All V305 rows | 88,351 | 39.56% | -0.70% | 51.75 | 4.47 | 0.00 |
| first120 horizon | 39,168 | 41.02% | -0.56% | 50.28 | 4.02 | 0.00 |

Mode-level:

| Mode | N | WR | Avg | SL% | GAP_SL% |
|---|---:|---:|---:|---:|---:|
| `MORNING60_HOLD` | 27,763 | 37.72% | -0.83 | 53.49 | 5.31 |
| `MORNING60_TAKEOVER` | 21,420 | 39.29% | -0.79 | 52.19 | 4.20 |
| `MORNING120_PERSIST` | 20,821 | 40.83% | -0.59 | 50.46 | 3.86 |
| `MORNING120_NO_FADE` | 18,347 | 41.23% | -0.53 | 50.07 | 4.19 |

Best leakage-clean pockets:

| Variant | N | WR | Avg | Month WR |
|---|---:|---:|---:|---|
| `MORNING120_PERSIST | GAP0_1 | RISK>=8 | IUP55_65 | SVR1.2_2` | 106 | 66.04% | +4.38 | 64.52 / 74.07 / 62.50 |
| `MORNING120_NO_FADE | GAP0_1 | RISK>=8 | IUP55_65 | SVR1.2_2` | 80 | 76.25% | +6.74 | 59.09 / 83.33 / 82.35 |
| `MORNING120_PERSIST | DD<-5 | PUSH3_6 | IUP55_65 | REL>=1` | 177 | 64.97% | +3.90 | 57.89 / 54.41 / 74.44 |
| `MORNING120_NO_FADE | RISK>=8 | MUP45_55 | IUP55_65` | 810 | 56.42% | +2.36 | 53.90 / 50.00 / 60.69 |
| `MORNING120_PERSIST | RISK>=8 | MUP45_55 | IUP55_65` | 935 | 56.68% | +2.44 | 47.26 / 54.11 / 62.62 |

## Interpretation

1. Waiting for the full morning improves **GAP_SL** materially versus V303/V304, but the overall WR/Avg remains negative because many candidates still fail after T+1 overnight.
2. The strongest signal is not raw market strength. The useful pattern is:
   - first120 no-fade/persistence;
   - industry up in the 55-65 band;
   - stock amount ratio 1.2-2.0;
   - moderate open gap or high-risk/high-reward setup.
3. The best large pocket, `MORNING120_NO_FADE | RISK>=8 | MUP45_55 | IUP55_65`, has 810 rows, WR 56.42%, Avg +2.36, and month WR 53.90/50.00/60.69 over 202604-202606. This is better than V304's largest stable pocket but still far below production expectations and only near-window 2026 coverage.
4. First60 is inferior to first120. The useful information appears after the whole morning proves no-fade/persistence, not merely first hour strength.
5. This closes the simple “wait longer in the morning + broad diffusion” branch as a standalone production route.

## Decision

Do not promote V305. Do not keep tuning first60/first120 threshold buckets on V302.

V305 produced a better diagnostic pocket than V304, but it remains a state/context layer rather than a standalone signal. The next useful direction should test more causal sources:

- true sector leadership propagation: leader stock/limit-up/large-turnover first, then peers;
- auction/opening gap source quality, not just gap size;
- order-flow or盘口 proxy if data is available;
- longer historical 15m data to see whether V305 pockets survive outside the near 2026 window.

## Verification

Focused ad-hoc verification should check:

- py_compile/import;
- helper bucket boundaries;
- source-row count 67,559;
- generated-row count 88,351;
- T+1 violations 0;
- no production/frontend/watchlist writes;
- top-variant selector fields are entry-time safe.
