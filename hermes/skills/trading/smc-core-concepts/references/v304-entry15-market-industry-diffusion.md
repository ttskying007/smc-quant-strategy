# V304 entry-session 15m market/industry diffusion audit

Date: 2026-07-04
Mode: no-write research audit. No production/frontend/watchlist writes.

## Hypothesis

V303 proved individual first/second 15m executable confirmation does not rescue V302. V304 tests a different entry-time information layer: whether the executable first/second 15m buy window has synchronized **market + industry participation** and stock amount persistence.

This is not another individual 15m threshold grid. It asks whether fake takeovers can be filtered by same-window market/industry diffusion.

## Source

- Script: `/root/.hermes/scripts/v25/v304_entry15_market_industry_diffusion_audit.py`
- Summary: `/root/.hermes/smc_audit/v304_entry15_market_industry_diffusion_latest.json`
- Rows: `/root/.hermes/smc_audit/v304_entry15_market_industry_diffusion_no_write_20260704_055030/v304_rows.csv`
- Input: V303 rows `/root/.hermes/smc_audit/v303_executable_15m_entry_timing_no_write_20260704_042957/v303_rows.csv`
- Industry map: `/root/.hermes/smc_audit/v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json`

## Method

For every V303 candidate, compute entry-time safe diffusion features from local 15m cache:

- `FIRST15_*` modes use only first 15m market/industry/stock features.
- `SECOND15_CONT` / `FIRST30_NO_DUMP` use first two 15m bars.
- `DAY_OPEN_BASE` is explicitly not allowed to use first/second 15m diffusion features.

Features:

| Feature group | Meaning |
|---|---|
| market up pct | percentage of all covered stocks up in the same first/second 15m cut |
| industry up pct | same but within the stock's Baostock industry |
| market / industry median return | same-window broad return pressure |
| industry median volume ratio | same-window amount persistence vs own previous 5 first-two-15m sessions |
| stock volume ratio | stock first-two-15m amount vs its previous 5-session baseline |
| stock relative return | stock 15m return minus its industry median return |

All rows preserve strict A-share T+1; exit replay is inherited from V303 and same-day buy/sell violations must remain 0.

## Results

Coverage:

| Metric | Value |
|---|---:|
| V303 rows | 168,940 |
| Rows with entry-time diffusion available | 101,384 |
| Coverage | 60.01% |
| 15m files | 4,653 |
| Symbol-date 15m feature rows | 223,222 |
| T+1 violations | 0 |

Baseline:

| Scope | N | WR | Avg | SL% | GAP_SL% | weakest month WR |
|---|---:|---:|---:|---:|---:|---:|
| All V303 rows | 168,940 | 38.91% | -0.735% | 48.82 | 9.79 | 17.31 |
| Diffusion-available rows | 101,384 | 38.59% | -0.795% | 51.82 | 6.29 | 18.39 |

Mode-level metrics remain poor:

| Mode | N | WR | Avg | Weakest month WR |
|---|---:|---:|---:|---:|
| `FIRST15_ACC_HOLD` | 30,192 | 38.80% | -0.774% | 25.93 |
| `FIRST15_TAKEOVER` | 22,943 | 40.45% | -0.689% | 19.05 |
| `SECOND15_CONT` | 19,561 | 38.86% | -0.733% | 6.67 |
| `FIRST30_NO_DUMP` | 28,688 | 36.71% | -0.943% | 16.67 |

Best leakage-clean variants:

| Variant | N | WR | Avg | Month WR |
|---|---:|---:|---:|---|
| `FIRST15_ACC_HOLD | ACC_MID1.5_3 | SWEEP0.6_1.2 | IUP55_65 | REL0_1` | 129 | 57.36% | +0.80% | 54.55 / 54.10 / 63.33 / 80.00 |
| `FIRST15_ACC_HOLD | GAP-2_0 | RISK3_5 | IUP55_65 | SVR0.8_1.2` | 195 | 54.36% | +0.46% | min 51.52 |
| `FIRST15_ACC_HOLD | MUP45_55 | IUP45_55 | IVR0.8_1.2` | 678 | 51.92% | +0.86% | min 51.06 |
| `FIRST30_NO_DUMP | DD-2_-0.5 | RISK>=8 | MUP<45 | IUP45_55` | 144 | 62.50% | +3.63% | min 50.00 |
| `SECOND15_CONT | GAP>=3 | RISK>=8 | IUP55_65 | SVR0.8_1.2` | 127 | 73.23% | +6.91% | min 47.06 |

## Interpretation

1. Same-window market/industry diffusion has real information: it lifts the best V303 pockets from ~52% WR to 57-73% WR in small pockets.
2. The lift is not enough for production. The largest stable-ish pocket with min-month WR above 50 has only 678 rows and only ~51.9% WR.
3. High-WR pockets are small and still weak-month fragile; they do not close the A-share T+1 overnight survival problem.
4. Industry up percentage is more useful than raw market up percentage, but it behaves as a state/context layer, not as a standalone signal.
5. `DAY_OPEN_BASE` was correctly protected from first/second 15m diffusion leakage; no future-feature routing was allowed for day-open rows.

## Decision

Do not promote V304. Do not keep tuning simple 15m market/industry up/volume buckets on top of V303.

V304 closes the simple “entry-session broad diffusion can rescue naive 15m lifecycle” branch. It helps but remains far below Lei's production expectation.

Next useful direction must be more causal than broad up-count:

- opening auction / call-auction gap quality and source;
- turnover/amount persistence across the whole morning, not only first 15/30m;
- true sector leadership propagation (leader → peers) rather than same-window industry up percentage;
- order-flow /盘口 proxy if data exists;
- longer 15m history to test whether these pockets survive outside 2026-near window.

## Verification

Focused ad-hoc verification PASS:

- py_compile/import;
- helper bucket boundary checks;
- metrics fixture checks;
- source-row count: 168,940;
- diffusion rows: 101,384;
- T+1 violations: 0;
- `DAY_OPEN_BASE` diffusion leakage rows: 0;
- top-variant selector field contract contains only entry-time fields.

This is focused verification, not full canonical test suite green.
