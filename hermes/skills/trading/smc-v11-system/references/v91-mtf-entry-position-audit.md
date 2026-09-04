# V91 MTF Entry Position Audit — entry location as SL root cause

Date: 2026-06-13

## Trigger

Use when Lei asks whether lower-timeframe / multi-cycle entry, previously filtered signals, entry price/location, or TP/SL/WR problems could be improved by adding another entry-position layer.

## Core finding

The large quality shift came from **entry price location inside the daily zone**, not from the current 60min reclaim entry model.

| Entry mode | n | WR | Avg PnL | SL rate | TP rate | Conclusion |
|---|---:|---:|---:|---:|---:|---|
| orig_v85_entry | 46,614 | 59.24% | +0.8629% | 36.21% | 55.40% | Main SL source |
| zone_high_limit | 46,612 | 81.06% | +1.6191% | 16.34% | 77.84% | Improved but still upper-zone risk |
| zone_mid_limit | 44,074 | 87.54% | +1.5320% | 12.15% | 84.61% | Best stable entry layer |
| zone_low_limit | 42,508 | 86.95% | +0.8197% | 13.05% | 77.80% | High WR but profit shrinks |
| m60_reclaim_close | 3,142 | 47.45% | +0.0598% | 46.50% | 46.05% | Do not productionize |
| m60_higher_low_reclaim | 3,400 | 34.74% | -0.6025% | 61.06% | 33.65% | Do not productionize |

## Production-candidate combos

| Combo | n | WR | Avg PnL | SL | TP | RR | Use |
|---|---:|---:|---:|---:|---:|---:|---|
| PASS + zone_mid + micro | 530 | 90.38% | +1.0998% | 9.43% | 90.00% | 1.5R | Primary V91 shadow candidate |
| PASS + zone_mid + liq | 530 | 89.25% | +1.4266% | 10.00% | 88.49% | 2.024R | Yield layer |
| PASS + zone_low + liq | 524 | 90.46% | +0.9184% | 9.54% | 83.40% | 2.219R | Defensive layer |
| RISK + zone_mid + micro | 5,891 | 90.24% | +1.3218% | 9.71% | 86.90% | 1.5R | Filtered-signal recovery candidate |
| RISK + zone_mid + liq | 5,891 | 89.76% | +1.6530% | 9.98% | 85.50% | 2.033R | Large-sample recovery/yield layer |
| RISK+HOLD_LAG + zone_mid + micro | 2,084 | 90.40% | +1.3285% | 9.60% | 89.20% | 1.5R | HOLD_LAG recovery candidate |

## Rules for future SMC SL audits

1. Do not start by widening stops or changing TP. First test entry-location layers: original confirmation price, zone_high, zone_mid, zone_low.
2. Treat risk/hold filters as coupled with entry location. `RISK` and `HOLD_LAG` rows can become high quality after zone_mid entry; do not hard-reject them before this matrix.
3. Current 60min reclaim implementation is not production-ready. 60min should first be tested as a **death/cancel filter** inside the zone, not as a chase-confirmation entry above zone_high.
4. Zone-high / confirmation-close entries are a common SL pollution bucket. Verify `zone_pos` and SL buckets before blaming signal direction.
5. Production promotion should be shadow-first: add a V91 scanner alongside V88, do not replace V88 baseline until forward/live execution and frontend order semantics support limit-entry waiting/canceling.

## Files from validation

- Script: `/root/.hermes/scripts/v25/v91_mtf_entry_position_audit.py`
- Report: `/root/.hermes/smc_opt_v91_mtf_entry_position_audit/v91_mtf_entry_position_report.json`
- Rows: `/root/.hermes/smc_opt_v91_mtf_entry_position_audit/v91_mtf_entry_position_rows.json`

Validation checks completed:

- Matrix rows: 186,350
- T+1 violations: 0
- Python compile: OK
- Required row fields present: symbol, entry_mode, tp_mode, entry_price, sl, tp1, tp2, tp3, rr, exit_date, pnl_pct
