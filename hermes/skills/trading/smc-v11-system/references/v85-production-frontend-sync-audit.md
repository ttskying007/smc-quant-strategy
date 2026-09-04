# V85 Production Gate + Frontend Sync Audit

Session date: 2026-06-12

## Trigger

Use this reference when working on SMC production promotion, frontend/backend synchronization, daily scan/live monitor parity, or when the user asks whether Kline/选股/实时/分析/复盘/共振 are all using the latest engine.

## Production result

V85 became the active production version when `/root/.hermes/smc_opt_v85_production_gate/v85_production_report.json` existed and `smc_unified.py` selected `ACTIVE_VERSION = V85`.

Production files:

- `/root/.hermes/smc_opt_v85_production_gate/v85_trades.json`
- `/root/.hermes/smc_opt_v85_production_gate/v85_picks.json`
- `/root/.hermes/smc_opt_v85_production_gate/v85_production_report.json`

V85 production metrics:

| Metric | Value |
|---|---:|
| n | 559 |
| WR | 89.09% |
| avg_pnl | +2.7117% |
| POI break | 9.30% |
| trend damage | 1.79% |
| TP rate | 88.91% |
| T+1 violations | 0 |
| field missing | 0 |

By year:

| Year | n | WR | avg_pnl |
|---|---:|---:|---:|
| 2023 | 110 | 86.36% | +2.1994% |
| 2024 | 132 | 88.64% | +2.5466% |
| 2025 | 233 | 90.56% | +2.9458% |
| 2026 | 84 | 89.29% | +2.9927% |

Production criteria all passed:

- total_n >= 500
- each year 2023–2026 n >= 50
- each year 2023–2026 WR >= 65%
- T+1 violations = 0
- field audit = 0 missing

## V85 mechanism summary

V85 production was not just a filter on V84. It used the V84 lesson that continuation and MIXED accumulation must be treated separately:

1. `CONTINUATION_EXPANDED_HOLD_ABOVE_POI`
2. `MIXED_ACCUMULATION_HOLD_ABOVE_POI`

Path results:

| Path | n | WR | avg_pnl |
|---|---:|---:|---:|
| CONTINUATION_EXPANDED_HOLD_ABOVE_POI | 294 | 87.07% | +2.6387% |
| MIXED_ACCUMULATION_HOLD_ABOVE_POI | 265 | 91.32% | +2.7927% |

Key lesson: `MIXED` must not be globally rejected. It must be split into `MIXED_ACCUMULATION` and `MIXED_DISTRIBUTION`; narrow POI + HOLD_ABOVE_POI inside MIXED can be a high-quality accumulation setup.

## Required frontend/backend verification after production promotion

Do not claim the system is fully synced just because the production report exists. Verify every surface separately.

### 1. Backend syntax/service

Minimum checks:

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py \
  /root/.hermes/scripts/v25/v82_smart_money_quality_gate.py \
  /root/.hermes/scripts/v25/v83_post_reclaim_takeover_gate.py \
  /root/.hermes/scripts/v25/v84_smart_money_path_split_gate.py
ss -ltnp | grep ':8890'
```

### 2. `/api/picks`

Required zero-blank checks:

- `pick_date` / `select_date`
- `join_date`
- `zone_type` or `zone_low` + `zone_high`
- `cost_line` / `smart_money_cost`
- `volatility_pct` / `risk_pct`
- engine should be `V85_PRODUCTION_GATE` after V85 promotion

In the verified V85 state:

| API | rows | blank pick | blank join | blank zone | blank cost | blank vol | engine |
|---|---:|---:|---:|---:|---:|---:|---|
| `/api/picks` | 559 | 0 | 0 | 0 | 0 | 0 | V85_PRODUCTION_GATE |

### 3. `/api/live-prices`

Zero blanks can pass while the live monitor is still reading old daily-scan/ledger state. Always check engine/source, not just fields.

Verified pitfall from V85 session:

| API | rows | blank fields | engine/source issue |
|---|---:|---:|---|
| `/api/live-prices` | 195 | 0 | sample rows still showed `V66_FULL_MARKET_SCAN` |

Interpretation: cost/zone/volatility were fixed, but daily scan/live monitor parity was not fully upgraded to V85.

### 4. Browser DOM checks

Check the actual tables, not just API.

For `/monitor`:

- Upper table “每日选股 → 实时监控” may still show legacy `V66_FULL_MARKET_SCAN` rows from the live monitor ledger.
- Lower table “当前有效选股” should show V85 rows, selection/join dates, Zone, cost line, volatility.
- In the verified V85 state, lower table had V85 559 picks, but quality was blank and SL/TP display showed incomplete values such as `SL=0.0%`, `TP:?`.

For `/live`:

- During market close, `现价` may be `-`; this is acceptable if `最后价格`, `行情状态`, `成本线`, `Zone`, and `波动` are populated.
- Still verify engine/source: V85 production promotion is incomplete if live rows still come from V66 daily scan.

### 5. Kline API/page

Check a production symbol, not only a random default.

Example verified call:

```text
/api/kline_full?symbol=002262.SZ&tf=daily
```

Observed V85 state:

- `version = V85`
- `signal_count = 108`
- `trade_count = 1`
- V85 trade marker existed
- background `signals_list` still included `UNAUDITED` / `PENDING_REPLAY` generic signals

Lesson: Kline can be V85 while still mixing production trade markers with unaudited historical/background signal markers. Future fixes should visually separate production trades from background signals.

### 6. Analysis/autopsy pages

A page title showing V85 is not enough. Verify the statistics make sense.

V85 pitfall:

- `/analysis` and `/autopsy` loaded as V85 pages but showed WR = `0.0%` while avg PnL was positive.
- Cause class: page aggregation used an older winner/field convention not fully compatible with V85 rows.
- Required fix direction: normalize V85 `won`, `pnl_pct`, `exit_reason`, `conf_type`, `sl_pct`, `tp_pct`, `rr` before calculating page statistics.

### 7. 90-day closed-loop review

V85 autopsy page still reported:

```text
未生成90日闭环复盘，请运行 v25/v49_closed_loop_90d_review.py
```

Do not treat autopsy as complete until a V85-specific 90-day closed-loop review is generated and displayed.

### 8. Resonance page

`/api/resonance` returned rows, but verified samples had `hourlyPos='?'`. Treat resonance as partially synced until weekly/daily/60min are all populated for V85 picks.

## Completion language

Use precise status language:

- Correct: “V85 production backend and `/api/picks` are live and field-complete; full frontend/live/analysis/autopsy/resonance sync is not complete.”
- Incorrect: “All frontend/backend data is fresh” unless live monitor engine, analysis/autopsy stats, Kline production/background separation, 90-day autopsy, and resonance all pass.

## Recommended next phase

Before further strategy invention, run a V86 frontend/backend sync release:

1. Switch daily scan/live monitor from V66 pipeline to V85 production gate.
2. Fix `/analysis` and `/autopsy` winner/statistics compatibility with V85.
3. Fill monitor quality/SL/TP display from V85 fields.
4. Generate and render V85 90-day closed-loop review.
5. Separate Kline production trade markers from unaudited background signal markers.
6. Populate resonance 60min fields for V85 picks.

Only after this can the system claim end-to-end V85 production sync.
