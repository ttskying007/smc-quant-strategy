# V303 executable 15m entry timing audit

Date: 2026-07-04
Mode: no-write research audit. No production/frontend/watchlist writes.

## Hypothesis

V302 proved naive 15m same-source ACC→MAN→DIS lifecycle generates many fake takeovers when bought blindly at next daily open. V303 tests whether **executable entry-day first/second 15m confirmation** can filter those fakes while preserving strict A-share T+1 exits.

## Source

- Script: `/root/.hermes/scripts/v25/v303_executable_15m_entry_timing_audit.py`
- Summary: `/root/.hermes/smc_audit/v303_executable_15m_entry_timing_latest.json`
- Rows: `/root/.hermes/smc_audit/v303_executable_15m_entry_timing_no_write_20260704_043116/v303_rows.csv`
- Input: V302 rows `/root/.hermes/smc_audit/v302_15m_same_source_lifecycle_no_write_20260703_202220/v302_rows.csv`

## Method

For each V302 candidate, generate entry modes that are actually observable at buy time:

| Mode | Buy price | Entry-time evidence |
|---|---|---|
| `DAY_OPEN_BASE` | entry-day daily open | only open gap vs prior ACC high; no first/second 15m future features |
| `FIRST15_ACC_HOLD` | first 15m close | first 15m holds above SL/ACC low and closes green |
| `FIRST15_TAKEOVER` | first 15m close | first 15m closes above ACC high and green |
| `SECOND15_CONT` | second 15m close | first+second 15m continuation above ACC/reclaim context |
| `FIRST30_NO_DUMP` | second 15m close | first 30m does not dump below ACC low and closes above open |

Important correction made during V303: initial run accidentally allowed `DAY_OPEN_BASE` variants to be mined using first-two-15m `push/dd` fields. The script was patched so every mode only exposes evidence available by that mode’s executable buy time. Verification checks `DAY_OPEN_BASE` has no future push/dd leakage.

Daily exits are strict T+1: exit replay starts from the trading day after entry date. Same-day buy/sell violations must remain 0.

## Results

Input coverage:

| Metric | Value |
|---|---:|
| V302 source rows | 67,559 |
| Eligible entry days with 15m bars | 67,559 |
| Missing entry-day 15m | 0 |
| V303 all-mode rows | 168,940 |
| Symbols | 4,591 |
| T+1 violations | 0 |

Mode-level result:

| Mode | N | WR | Avg | SL% | GAP_SL% | Weakest month WR |
|---|---:|---:|---:|---:|---:|---:|
| `FIRST15_ACC_HOLD` | 30,192 | 38.80% | -0.774% | 51.34 | 6.85 | 25.93 |
| `FIRST15_TAKEOVER` | 22,943 | 40.45% | -0.689% | 50.95 | 4.83 | 19.05 |
| `FIRST30_NO_DUMP` | 28,688 | 36.71% | -0.943% | 52.79 | 7.45 | 16.67 |
| `DAY_OPEN_BASE` | 67,556 | 39.39% | -0.645% | 44.31 | 15.05 | 15.94 |
| `SECOND15_CONT` | 19,561 | 38.86% | -0.733% | 52.18 | 5.42 | 6.67 |

Best leakage-clean large-ish pockets remain far below production:

| Variant | N | WR | Avg | Weakest month WR |
|---|---:|---:|---:|---:|
| `FIRST15_ACC_HOLD | GAP-2_0 | DD<-5 | RISK>=8` | 432 | 52.08% | +1.43% | 49.51 |
| `FIRST15_TAKEOVER | GAP-2_0 | DD<-5 | RISK>=8` | 415 | 52.05% | +1.45% | 49.02 |
| `FIRST30_NO_DUMP | GAP1_3 | DD-2_-0.5 | RISK>=8` | 320 | 51.56% | +0.92% | 42.11 |

## Interpretation

Executable first/second 15m timing does **not** rescue the 15m same-source lifecycle branch:

1. Waiting for first/second 15m confirmation reduces GAP_SL but increases regular SL and does not improve WR.
2. The best leakage-clean pockets are only ~52% WR and still weak-month fragile.
3. Many 15m takeovers are fake not because entry is too early by one bar, but because the underlying lifecycle definition is not identifying real operator takeover.
4. A-share T+1 remains the structural execution problem: intraday micro confirmation can look valid, but the position still must survive overnight/next day.

## Decision

Do not promote V303. Do not continue tuning first/second 15m timing thresholds on top of V302.

This branch closes the simple “更细周期 + 可执行买点确认” hypothesis. The next useful direction cannot be another threshold grid over the same 15m lifecycle. It must add a new information layer available before/at buy time, for example:

- auction/opening-call quality and gap source;
- real sector synchronized intraday expansion, not only individual 15m bars;
- turnover/amount persistence versus stock’s own historical DNA;
- longer minute history or order-flow/盘口 proxy.

## Verification

Focused ad-hoc verification PASS:

- py_compile/import;
- helper bucket boundary checks;
- entry-time feature availability contract;
- summary no-write/source/T+1 contract;
- real row artifact count: 168,940 rows;
- T+1 violations = 0;
- `DAY_OPEN_BASE` future-feature violations = 0;
- no `first2_*` leakage fields remain in V303 row artifact.

This is focused verification, not full canonical test suite green.
