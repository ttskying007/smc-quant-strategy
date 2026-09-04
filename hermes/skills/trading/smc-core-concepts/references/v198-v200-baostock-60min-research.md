# V198-V200 Baostock historical 60min research closure

Date: 2026-06-25

## Trigger
Use when continuing post-V175 SMC research after V177-V197, especially if considering true historical intraday data as the next qualitative information layer.

## Fixed gates
Production intraday upgrade usable:
- source/execution rule must be executable without outcome leakage;
- T+1 violations = 0;
- `n >= 247` for V175 replacement replay;
- `min_year_n >= 38`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- shadow-only until all gates pass.

## V198 — Baostock 60min feasibility + TIME-row diagnostic
Artifact: `/root/.hermes/smc_audit/v198_baostock_60min_time_rows_fast_20260625_203624/`

### Source-safety correction (2026-07-11)

- `query_history_k_data_plus(...frequency='60')` silently caps one response at **1,500 bars**. A `2023–2026` request can therefore look successful while ending around mid-2024. Full-history research must query **one calendar year per call** and validate every returned daily date and all four slots (`10:30/11:30/14:00/15:00`) against the daily source.
- Execution and causal intraday feature research must use **`adjustflag='3'` raw OHLCV**. On `600519`, the price ratio of adjusted to raw data changed around corporate-action dates; a retrospectively adjusted series can embed later corporate-action factors. Adjusted intraday data may be used only for display diagnostics, never as a trade-generation or fill source.
- The strict full-universe source audit is `/root/.hermes/scripts/v25/v371_baostock_m60_strict_coverage_audit.py`; it is source-only and must pass before an MTF generator can run.

Result:
- Baostock 60min data is available historically across 2023-2026 for V175 TIME rows.
- Fetch ok: `65/65`; per-trade span rows `12-44`.
- TIME row class counts:
  - `HELD_REASONABLE=29`
  - `NEAR_TP_NO_HIT=16`
  - `MID_MFE_GIVEBACK=12`
  - `NO_FOLLOW_THROUGH=7`
  - `INTRADAY_TP_REACHABLE=1`
- Base TIME metrics: `n=65`, `WR=72.31%`, `Avg=2.0883%`, `Median=2.6907%`.
- Close-fail executable subset: `n=32`, `WR=81.25%`, `Avg=0.85%`; not useful due low Avg / micro-profit behavior.

Interpretation: the old V179 “60min coverage insufficient” is true for Tencent/Eastmoney limited endpoints, but Baostock provides enough historical 60min for targeted V175 intraday diagnostics. However TIME rows are not a single homogeneous fixable bug; most are either reasonable holds or near-TP misses, not obvious intraday exit failures.

## V199 — full V175 60min replay
Artifact: `/root/.hermes/smc_audit/v199_baostock_60min_full_v175_replay_20260625_204034/`

Result:
- Decision: `V199_INTRADAY_REPLAY_NO_PRODUCTION_UPGRADE`.
- Fetch ok: `247/247`; missing `0`; T+1 violations `0`.
- Best/closest variant `base_60m`:
  - `n=247`, `WR=85.43%`, `Avg=6.1185%`, `Median=7.3367%`
  - `min_year_n=38`, yearly WR: 2023 `82.98%`, 2024 `86.59%`, 2025 `85.0%`, 2026 `86.84%`
  - `all_year_WR_min=82.98%`, `micro_profit_pct=1.62%`, T+1 `0`
  - exits: `TP_60M=154`, `TIME_60M_CLOSE=73`, `SL_60M=18`, `GAP_SL_60M=2`
- This improves WR and Avg versus V175 (`+1.62pp WR`, `+0.0692 Avg`) but fails production gate on `Avg < 6.2` and `micro > 1%`.
- Profit-lock/close-fail variants raised WR (up to ~90%) but cut Avg and increased micro-profit pollution; unusable.

Interpretation: historical 60min replay is a real new information layer and slightly improves V175, but not enough to promote. It should remain research-only unless a later executable intraday rule clears Avg and micro gates together.

## V200 — 60min TP/hold grid
Artifact: `/root/.hermes/smc_audit/v200_baostock_60min_tp_hold_grid_20260625_204911/`

Result:
- Decision: `V200_INTRADAY_TP_HOLD_GRID_NO_PRODUCTION_PASS`.
- Production pass count: `0`.
- Best Avg variant: `rr2.5_h15_sl`: `n=247`, `WR=74.49%`, `Avg=7.2736%`, `all_year_WR_min=65.79%`, `micro=2.43%`, T+1 `0` — high Avg but year/WR fail.
- Closest balanced variant: `rr2.5_h15_lock03_1r`: `n=247`, `WR=87.85%`, `Avg=6.844%`, `all_year_WR_min=85.0%`, `micro=2.43%`, T+1 `0` — fails only micro gate, but micro pollution is above fixed threshold and cannot be ignored.
- Other high-Avg variants sacrifice WR/year stability; high-WR variants lower Avg or create micro-profit pollution.

Interpretation: 60min TP/hold optimization discovers a near-frontier but not a production-safe upgrade. Do not promote by weakening micro-profit gate.

## Failed V201 attempt
A follow-up profit-lock grid (`/tmp/v201_60m_profit_lock_grid.py`) hit Baostock connection resets/broken pipes after ~200 fetches and failed with missing spans. Treat as incomplete, not evidence. If continuing, add persistent per-trade 60min cache + retry/relogin before running larger grids.

## Current conclusion after V200
- V175 remains production baseline.
- Baostock historical 60min is now validated as a usable research data source.
- No V198-V200 intraday variant passes the declared production gate.
- The most promising near-frontier is not a new signal engine but an execution-layer candidate: `rr2.5_h15_lock03_1r` has strong WR/Avg/year stability but fails micro (`2.43%`).

## Next concrete direction
Do not mutate production. Next research should build a cached/retry-safe Baostock 60min dataset for V175 and run a constrained micro-resolution study:
1. cache all per-trade 60min bars locally to avoid Baostock resets;
2. start from `rr2.5_h15_lock03_1r`;
3. test only executable rules that reduce micro-profit without using final outcome, e.g. lock only if profit-lock distance exceeds 1% absolute, or convert low absolute lock to no-lock;
4. pass only if `WR>=84`, `Avg>=6.2`, `yearMin>=82`, `micro<=1`, T+1=0.

If that fails, intraday execution layer should be closed and next qualitative work must use intraday features at candidate creation time, not just exit replay.

## Superseded follow-up: V371–V374 Sina full-history cache + causal generator (2026-07-12)

Do not rely on Baostock as the only historical source: on 2026-07-12 its login returned `10001011 黑名单用户` in this environment.

A resumable Sina 60-minute raw cache was acquired for the current local universe:

- builder: `/root/.hermes/scripts/v25/v371_sina_m60_dataset_build.py`
- strict audit: `/root/.hermes/scripts/v25/v373_sina_m60_strict_coverage_audit.py`
- cache: `/root/.hermes/intraday_cache/sina_m60_v1/`
- universe: 4,655 symbols; 4,654 have local daily dates in 2023–2026
- calendar-date gaps: **0** across 3,425,780 expected daily dates
- hard source slot defects: 15 dates in 11 symbols (all must be explicit per-day boundaries, never silently filled)

### V374 full-history causal M60 test

Artifact/script: `/root/.hermes/scripts/v25/v374_m60_causal_retest_generator.py`

This is a genuinely new candidate generator, not a V175 exit overlay:

`confirmed 3/3 SSL sweep → close MSS → event-anchored bearish OB → first touch → reclaim → hold → next M60 open`

- all sequence fields are recorded; all 4,089 completed rows passed strict time ordering
- raw intraday data only; invalid source days excluded as hard boundaries
- T+1 violations: 0
- results: n=4,089, WR=33.41%, AvgPnL=+0.0117%, SL=65.22%; year WR: 2023 27.78%, 2024 34.11%, 2025 34.63%, 2026 36.94%
- production gate: **failed decisively** (only n/min-year/sample T+1/micro gates passed)

**Closure:** do not tune V374 thresholds, exits, or RR. This complete intraday sequence is not a usable A-share daily/60m long generator. It proves that full historical intraday availability alone does not validate the individual-stock sweep→MSS→OB-retest hypothesis.

## Valid next qualitative direction

If research continues, do not revisit individual-bar scalar filtering or exits. The next information layer must be **cross-sectional/contextual before candidate creation** (e.g. market/industry synchronized liquidity and participation state), with strict point-in-time membership and an independently re-derived causal event chain. It must first prove a new signal definition, then meet the fixed production gate; no current V198–V200 or V374 output may be promoted.