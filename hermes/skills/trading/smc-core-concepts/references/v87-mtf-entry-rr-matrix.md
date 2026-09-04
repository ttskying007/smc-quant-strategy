# V87 MTF Entry RR Matrix Lesson

Session date: 2026-06-13

## Trigger

Use after V86 production when the user asks for multi-timeframe, smaller timeframe entry, TP/SL/RR matrix, full closure, or low-RR repair.

## Inputs

- Source: `/root/.hermes/smc_opt_v86_production_gate/v86_trades.json` (532 rows)
- 60min cache: `/root/.hermes/kline_cache_60min/*_60min_500.json`
- Daily/weekly cache: `/root/.hermes/kline_cache/*_daily_750.json`, `*_weekly_200.json`

## Files

- Script: `/root/.hermes/scripts/v25/v87_mtf_entry_rr_matrix.py`
- Tests: `/root/.hermes/scripts/v25/test_v87_mtf_entry_rr_matrix.py`
- Output dir: `/root/.hermes/smc_opt_v87_mtf_entry_rr_matrix/`
- Main report: `/root/.hermes/smc_opt_v87_mtf_entry_rr_matrix/v87_report.md`

## Matrix dimensions

Entry modes:

- `daily_next_open`
- `zone_limit`
- `m60_reclaim`
- `m60_higher_low`
- `m60_mss`

SL modes:

- `daily_zone_buffer`
- `m60_swing_low`
- `m60_reclaim_low`
- `hybrid_tight`

TP modes:

- `rr_1_2_3`
- `rr_1_5_3`
- `liq_then_2r_runner`
- `micro_0_8_1_5_3`

Output contract fields:

- `weekly_state`, `daily_state`, `m60_state`, `mtf_score`
- `entry_price`, `sl`, `tp1`, `tp2`, `tp3`, `rr`, `rr_realized`
- `exit_legs`, `mfe_pct`, `mae_pct`, `mfe_r`, `mae_r`

Field audit after rerun: 0 missing.

## Test result

5/5 passed:

1. 60min window uses only entry day + next day.
2. m60 reclaim uses reclaim close and intraday swing SL.
3. invalid/tiny risk RR is rejected.
4. TP1/TP2/runner plus MFE/MAE R are output.
5. daily state distinguishes bull/recovery/bear.

## Key results

Total matrix rows: 20,908.

Overall:

| n | WR | avg pnl | avg RR | low RR | avg MFE R |
|---:|---:|---:|---:|---:|---:|
| 20,908 | 78.69% | +1.9326% | 1.8159R | 0.00% | 3.795R |

Entry mode comparison:

| entry_mode | n | WR | avg pnl | avg MFE R |
|---|---:|---:|---:|---:|
| zone_limit | 8,512 | 82.40% | +1.9930% | 4.108R |
| daily_next_open | 8,512 | 80.93% | +1.9572% | 4.016R |
| m60_reclaim | 1,488 | 68.55% | +1.8012% | 2.690R |
| m60_higher_low | 1,516 | 67.74% | +1.7426% | 2.718R |
| m60_mss | 880 | 57.05% | +1.6601% | 2.353R |

TP mode comparison:

| tp_mode | WR | avg pnl | avg RR |
|---|---:|---:|---:|
| liq_then_2r_runner | 76.33% | +2.4773% | 2.2635R |
| rr_1_2_3 | 76.93% | +1.8942% | 2.0000R |
| rr_1_5_3 | 79.87% | +1.7094% | 1.5000R |
| micro_0_8_1_5_3 | 81.61% | +1.6495% | 1.5000R |

## Best production-like combos

Yield-first:

| combo | n | WR | avg pnl | avg RR |
|---|---:|---:|---:|---:|
| `daily_next_open + daily_zone_buffer + liq_then_2r_runner` | 532 | 77.07% | +2.9635% | 2.1271R |
| `zone_limit + daily_zone_buffer + liq_then_2r_runner` | 532 | 78.20% | +2.9540% | 2.1329R |
| `zone_limit + hybrid_tight + liq_then_2r_runner` | 532 | 83.65% | +2.8393% | 2.4228R |

Win-rate-first:

| combo | n | WR | avg pnl | avg RR |
|---|---:|---:|---:|---:|
| `zone_limit + hybrid_tight + micro_0_8_1_5_3` | 532 | 89.10% | +1.8125% | 1.5000R |
| `daily_next_open + hybrid_tight + micro_0_8_1_5_3` | 532 | 87.97% | +1.7972% | 1.5000R |
| `zone_limit + hybrid_tight + rr_1_5_3` | 532 | 87.78% | +1.8976% | 1.5000R |

## Multi-timeframe conclusion

For `zone_limit + hybrid_tight + micro_0_8_1_5_3`:

| mtf_score | n | WR | avg pnl | avg MFE R |
|---:|---:|---:|---:|---:|
| 0 | 1 | 0.00% | -1.7604% | 0.786R |
| 1 | 63 | 80.95% | +1.2772% | 2.806R |
| 2 | 247 | 87.04% | +1.6960% | 4.084R |
| 3 | 221 | 94.12% | +2.1114% | 4.899R |

MTF resonance works: score 3 is materially better.

## Critical limitation

60min entry is not production-ready because 60min cache only covers recent data:

| m60 entry | executable source candidates | distribution |
|---|---:|---|
| m60_reclaim | 90 | mostly 2025/2026; only 4 in 2023 and 4 in 2024 |
| m60_higher_low | 92 | mostly 2025/2026 |
| m60_mss | 54 | mostly 2025/2026 |

Do not use 60min entry as a production hard gate until full historical 60min coverage exists.

## Decision

V87 is research-only. It completes the TP/SL/RR/MTF matrix and fixes the missing output contract, but it should not replace V86 directly.

Next: V88 should solidify two production candidates:

1. V88-A yield-first: `daily_next_open + daily_zone_buffer + liq_then_2r_runner`.
2. V88-B win-rate-first: `zone_limit + hybrid_tight + micro_0_8_1_5_3`.

Both must emit the complete V87 output contract and then be frontend-synced.
