# SMC 继续执行恢复报告 — 2026-06-24 08:52 CST

## 结论

- 08:30 的 morning push 父进程已因外层超时退出，但子进程 `smc_daily_ops.py` 没有失败；已等到 08:51:43 完成。
- 今日 K 线覆盖率已从凌晨异常的 `4154/4905` 恢复到 `4655/4905`，最新日 `20260623` 覆盖 `4639` 只；completeness gate 恢复通过口径。
- Shadow selector 全部 `returncode=0`，无 timeout。
- 前端当前生产展示为 `V175`，API smoke 全部通过。
- 当前 `/api/live-prices` 返回 26 条候选，但 live guard 显示：`23 NON_TRADABLE_CONTEXT`、`3 NO_LIVE_LAST_PRICE`，没有可立即买入的新生产候选。

## 日闭环/早盘恢复结果

| 项目 | 结果 |
|---|---:|
| generated_at | 2026-06-24T08:51:43 |
| data_date | 20260623 |
| K线 requested | 4905 |
| K线 ok | 4655 |
| K线 failed | 250 |
| 最新日 20260623 覆盖 | 4639 |
| top_errors | {"rows=1": 247, "rows=42": 2, "rows=0": 1} |
| daily_scan | V90_DAILY_SCANNER_GENERATED_ACTIVE_PICKS_WITH_V88_CONTRACT |
| shadow_returncode | 0 |
| shadow_duration_sec | 945.1 |

## Shadow stages

| 脚本 | 秒 | returncode | timeout |
|---|---:|---:|---|
| v98_reachable_5r_probability_gate.py | 570.3 | 0 | False |
| v99_high_wr_production_gate.py | 37.5 | 0 | False |
| v100_structural_net_gate.py | 15.4 | 0 | False |
| v101_mtf_dna_combo_contract.py | 321.9 | 0 | False |

## 前端 API 状态

| 字段 | 值 |
|---|---:|
| version | V175 |
| engine | V175_DEMAND_OB_TRUE_TAKEOVER_SEMANTIC_SPLIT |
| total_trades | 247 |
| win_rate | 83.8 |
| avg_pnl | 6.05 |
| stocks | 236 |
| pick_contract.tradable_active_pick_count | 26 |
| pick_contract.active_pick_count | 26 |
| pick_contract.watch_only_count | 0 |
| pick_contract.raw_pick_file_count | 26 |
| data_status.last_kline_date | 20260623 |
| data_status.last_trade_date | 20260617 |
| data_status.data_age_days | 6 |

## live guard 状态计数

| 状态 | 数量 |
|---|---:|
| NO_LIVE_LAST_PRICE | 3 |
| NON_TRADABLE_CONTEXT | 23 |

## `/api/live-prices` 26条候选明细

| 代码 | 日期 | 成本 | 当前 | PnL% | SL | TP | 状态 |
|---|---:|---:|---:|---:|---:|---:|---|
| 002401.SZ | 20260615 | 12.29 | 12.81 | 0.87 | 12.04 | 13.69 | NO_LIVE_LAST_PRICE |
| 688327.SH | 20260617 | 13.22 | 13.82 | 0.00 | 12.83 | 15.30 | NO_LIVE_LAST_PRICE |
| 603568.SH | 20260611 | 15.26 | 15.50 | -1.34 | 14.93 | 16.88 | NO_LIVE_LAST_PRICE |
| 300757.SZ | 20260616 | 608.66 | 578.20 | 0 | 592.23 | 687.46 | NON_TRADABLE_CONTEXT |
| 688048.SH | 20260616 | 341.46 | 392.05 | 0 | 325.57 | 414.02 | NON_TRADABLE_CONTEXT |
| 688376.SH | 20260616 | 73.58 | 79.66 | 0 | 70.69 | 89.10 | NON_TRADABLE_CONTEXT |
| 688486.SH | 20260616 | 50.58 | 57.00 | 0 | 49.45 | 58.07 | NON_TRADABLE_CONTEXT |
| 000567.SZ | 20260615 | 5.55 | 6.17 | 0 | 5.40 | 6.11 | NON_TRADABLE_CONTEXT |
| 688277.SH | 20260615 | 16.80 | 19.15 | 0 | 16.14 | 19.64 | NON_TRADABLE_CONTEXT |
| 300568.SZ | 20260612 | 17.07 | 18.94 | 0 | 16.64 | 18.69 | NON_TRADABLE_CONTEXT |
| 600259.SH | 20260612 | 88.39 | 106.79 | 0 | 85.90 | 106.12 | NON_TRADABLE_CONTEXT |
| 002850.SZ | 20260611 | 178.61 | 184.58 | 0 | 174.35 | 207.03 | NON_TRADABLE_CONTEXT |
| 688156.SH | 20260611 | 24.43 | 27.66 | 0 | 23.87 | 27.42 | NON_TRADABLE_CONTEXT |
| 002368.SZ | 20260610 | 15.29 | 16.73 | 0 | 14.96 | 16.41 | NON_TRADABLE_CONTEXT |
| 002643.SZ | 20260610 | 13.65 | 17.74 | 0 | 13.32 | 15.08 | NON_TRADABLE_CONTEXT |
| 002937.SZ | 20260610 | 33.47 | 41.80 | 0 | 32.75 | 38.38 | NON_TRADABLE_CONTEXT |
| 300637.SZ | 20260610 | 9.58 | 10.57 | 0 | 9.38 | 10.71 | NON_TRADABLE_CONTEXT |
| 600392.SH | 20260610 | 22.59 | 31.03 | 0 | 22.01 | 25.54 | NON_TRADABLE_CONTEXT |
| 603072.SH | 20260610 | 35.04 | 40.00 | 0 | 34.25 | 38.27 | NON_TRADABLE_CONTEXT |
| 688035.SH | 20260610 | 73.38 | 95.06 | 0 | 71.78 | 84.84 | NON_TRADABLE_CONTEXT |
| 688138.SH | 20260610 | 30.61 | 38.22 | 0 | 29.99 | 35.19 | NON_TRADABLE_CONTEXT |
| 688721.SH | 20260610 | 39.95 | 52.19 | 0 | 38.87 | 45.40 | NON_TRADABLE_CONTEXT |
| 603638.SH | 20260609 | 22.00 | 23.97 | 0 | 21.42 | 26.24 | NON_TRADABLE_CONTEXT |
| 002631.SZ | 20260608 | 6.84 | 8.99 | 0 | 6.66 | 8.01 | NON_TRADABLE_CONTEXT |
| 603161.SH | 20260605 | 13.94 | 15.54 | 0 | 13.63 | 16.28 | NON_TRADABLE_CONTEXT |
| 000630.SZ | 20260529 | 6.48 | 7.14 | 0 | 6.32 | 7.55 | NON_TRADABLE_CONTEXT |

## 文件

- ops_latest: `/root/.hermes/smc_monitor/ops_latest.json`
- ops_log: `/root/.hermes/smc_monitor/ops_logs/20260624.json`
