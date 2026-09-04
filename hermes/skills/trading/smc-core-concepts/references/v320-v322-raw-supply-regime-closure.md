# V320-V322 raw supply / regime continuation closure

Session date: 2026-07-08

Use after V316-V319 when continuing the standing goal to research different directions until a production-improvement candidate appears.

## Fixed production-improvement gate

| Gate | Threshold |
|---|---:|
| n | >=300 |
| min_year_n | >=40 |
| net WR (`pnl_pct>=0.8%`) | >=87% |
| AvgPnL | >=6.8% |
| all_year_WR_min | >=84% |
| micro_profit_pct | <=1% |
| T+1 violations | 0 |

## V320 raw compression -> breakout -> retest -> reclaim

Scripts:

- Full grid attempted: `/root/.hermes/scripts/v25/v320_raw_compression_breakout_retest_generator.py` — timed out at 600s, so do not rely on partial output.
- Fast representative matrix: `/root/.hermes/scripts/v25/v320_fast_raw_compression_breakout_retest_generator.py`

Artifact:

`/root/.hermes/smc_audit/v320_fast_raw_compression_breakout_retest_latest.json`

Result:

| Item | Value |
|---|---:|
| usable symbols | 4618 |
| configs | 30 |
| production pass | 0 |
| best config | L20_R12_B1.5_W8_T1.0_RR1.2_H10 |
| best n | 3816 |
| best WR | 44.9948% |
| best Avg | 0.2298% |
| V185 overlap | 0 |

Conclusion: raw compression-breakout-retest is a very broad non-overlapping supply source, but quality is far below production. Close this simple version.

## V321 raw SSL sweep -> reclaim

Scripts:

- Full grid attempted: `/root/.hermes/scripts/v25/v321_raw_ssl_sweep_reclaim_generator.py` — timed out at 600s, so use fast result.
- Fast representative matrix: `/root/.hermes/scripts/v25/v321_fast_raw_ssl_sweep_reclaim_generator.py`

Artifact:

`/root/.hermes/smc_audit/v321_fast_raw_ssl_sweep_reclaim_latest.json`

Result:

| Item | Value |
|---|---:|
| usable symbols | 4618 |
| configs | 24 |
| production pass | 0 |
| best config | L60_P0.8_D2_C0.65_RR1.2_H10 |
| best n | 25,518 |
| best WR | 47.8956% |
| best Avg | 0.2686% |
| V185 overlap | 7 |

Conclusion: raw SSL sweep+reclaim alone produces too many false positives and is not a production-quality SMC event. Close this simple version.

## V322 market breadth environment overlay on V185

Script:

`/root/.hermes/scripts/v25/v322_market_breadth_overlay_audit.py`

Artifact:

`/root/.hermes/smc_audit/v322_market_breadth_overlay_latest.json`

Result:

| Item | Value |
|---|---:|
| daily breadth dates | 1725 |
| V185 rows | 334 |
| features | market_adv_pct, market_avg_ret_pct, market_adv5_pct, market_avg5_ret_pct |
| single rules | 83 |
| pair rules | 434 |
| production pass | 0 |
| best rule | `market_avg5_ret_pct>=-0.5154 AND market_avg_ret_pct>=0.5147` |
| best n | 144 |
| best WR | 91.6667% |
| best Avg | 7.1623% |
| best min_year_n | 8 |

Conclusion: market breadth identifies a high-quality pocket, but it collapses yearly coverage and cannot promote. It is a diagnostic tag, not a production gate.

## Closed branches added

1. Simple raw compression-breakout-retest generator.
2. Simple raw SSL sweep-reclaim generator.
3. Full-market breadth overlay as V185 production filter.

## Root lesson

Raw daily events have high supply but poor precision. V185 works because it captures true-takeover semantics; broad raw patterns do not. The next viable generator must explicitly prove post-event absorption/takeover persistence, not just pattern occurrence.
