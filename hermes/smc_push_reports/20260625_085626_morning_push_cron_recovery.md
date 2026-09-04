# SMC 早盘持仓 + 每日活跃选股推送恢复报告（20260625）

## 结论
- 原始 `v25/smc_morning_push.py` 被 cron/data-collection wrapper 在 120s 超时；后续发现孤儿 `smc_daily_ops.py` 仍在继续运行，未重复启动同类任务。
- 已等待 PID 1985918 完成；最终 `smc_daily_ops.py` 已退出，残留检查未发现 `smc_morning_push/smc_daily_ops/v98/v99/v100/v101` 子进程。
- `ops_latest.json` 已刷新：generated_at=2026-06-25T08:49:05，data_date=20260624。
- 前端 API smoke 成功：`/api/summary`、`/api/autopsy/closed-loop`、`/api/picks`、`/api/live-prices`、`/api/resonance`、`/api/monitor/state` 均 HTTP 200。
- 持仓：OPEN 原始 129，去重后 129；NEXT_DAY_PENDING 0。
- 活跃选股：`/api/picks` 返回 26 条，生产 active_pick_count=26，live guard 可交易 4 / 观察 22；当前市场状态：休市 (交易时间: 周一至周五 9:30-11:30, 13:00-15:00)。

## 数据刷新 / 门禁状态
- K线刷新脚本：returncode=0，duration=151.6s。
- 刷新遥测：requested=4905，ok=3213，failed=1692，latest_counts={'20260624': 3203, '20260623': 1, '20260413': 1, '20260527': 1, '20260622': 3, '20210528': 1, '20260430': 2, '20260616': 1}。
- 缓存复核：kline_cache 有 4655 个有效缓存，最新交易日 20260624 覆盖 4637 只；按缓存折算 effective_failed=268（5.46%）。
- 判定：刷新遥测存在供应商空响应/计数失真，但缓存覆盖满足生产完整性阈值（>=4500 且 effective failed <=8%）。
- Daily scan：{'ok': True, 'reason': 'V90_DAILY_SCANNER_GENERATED_ACTIVE_PICKS_WITH_V88_CONTRACT'}
- Shadow selector：returncode=0，duration=726.4s。
  - Stage 1: v98_reachable_5r_probability_gate.py returncode=0 timed_out=False duration=517.7s
  - Stage 2: v99_high_wr_production_gate.py returncode=0 timed_out=False duration=20.9s
  - Stage 3: v100_structural_net_gate.py returncode=0 timed_out=False duration=13.3s
  - Stage 4: v101_mtf_dna_combo_contract.py returncode=0 timed_out=False duration=174.5s

## 前端版本 / 策略摘要
- version=V175，engine=V175_DEMAND_OB_TRUE_TAKEOVER_SEMANTIC_SPLIT，trades=247，WR=83.8%，avg_pnl=6.05%。
- pick_contract={'tradable_active_pick_count': 26, 'rejected_active_pick_count': 0, 'active_pick_count': 26, 'active_pick_count_including_reject': 26, 'historical_best_count': 0, 'watch_only_count': 0, 'raw_pick_file_count': 26, 'active_picks_not_historical_all_market': True, 'contract_note': 'Scoped pick contract enabled.'}
- data_status={'last_kline_date': '20260624', 'last_trade_date': '20260617', 'data_age_days': 7, 'note': '5月信号稀少: bear sweep on 2026-05-14 suppresses bull signals (normal SMC behavior)'}

## `/api/picks` / live guard 分布
- pick_scope 分布：{'ACTIVE_CANDIDATE': 26}
- pick status 分布：{'ACTIVE_BUY_VALID': 4, 'WATCH_ONLY_CONTEXT': 22}
- live guard status 分布：{'NO_LIVE_LAST_PRICE': 4, 'NON_TRADABLE_CONTEXT': 22}

## OPEN 持仓明细（去重后 129 条，全部列出）
| # | 标记 | 选股日 | 买入/加入日 | 代码 | 名称 | 成本/入场 | 当前价 | PnL | SL | TP1 | 状态 | 信号类型 | 序列 |
|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| 1 | [已持仓] | 20260609 | 2026-06-09T15:22:51 | 601088.SH | - | 48.75 | 40.05 | -17.85% | 46.98 | 51.42 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull |
| 2 | [已持仓] | 20260609 | 2026-06-09T15:22:51 | 601398.SH | - | 7.57 | 7.22 | -4.62% | 7.18 | 8.04 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull |
| 3 | [已持仓] | 20260609 | 2026-06-09T15:22:51 | 603060.SH | - | 7.16 | 6.34 | -11.45% | 6.84 | 7.65 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull |
| 4 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 000001.SZ | - | 11.29 | 10.51 | -6.91% | 10.95 | 11.81 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 5 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 000785.SZ | - | 2.35 | 2.09 | -11.06% | 2.29 | 2.46 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 6 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 000929.SZ | - | 9.27 | 9.68 | +4.42% | 8.96 | 9.74 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 7 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 000977.SZ | - | 59.18 | 64.80 | +9.50% | 57.46 | 61.87 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 8 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002058.SZ | - | 22.76 | 20.93 | -8.04% | 21.75 | 24.31 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 9 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002108.SZ | - | 4.63 | 4.68 | +1.08% | 4.49 | 4.85 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 10 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002192.SZ | - | 79.19 | 93.39 | +17.93% | 77.17 | 82.80 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 11 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002210.SZ | - | 2.56 | 2.21 | -13.67% | 2.45 | 2.73 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 12 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002297.SZ | - | 21.18 | 33.66 | +58.92% | 20.31 | 22.70 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 13 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002331.SZ | - | 8.31 | 7.87 | -5.29% | 7.97 | 8.82 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 14 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002335.SZ | - | 36.65 | 38.42 | +4.83% | 35.58 | 38.30 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 15 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002415.SZ | - | 30.21 | 34.03 | +12.64% | 29.39 | 31.50 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 16 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002512.SZ | - | 4.09 | 3.67 | -10.27% | 3.94 | 4.33 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 17 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002515.SZ | - | 7.39 | 10.61 | +43.57% | 7.13 | 7.81 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 18 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002606.SZ | - | 13.58 | 14.25 | +4.93% | 13.06 | 14.44 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 19 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002637.SZ | - | 11.46 | 11.13 | -2.88% | 10.99 | 12.16 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 20 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002678.SZ | - | 5.59 | 4.47 | -20.04% | 5.42 | 5.86 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 21 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002824.SZ | - | 27.28 | 38.30 | +40.40% | 26.30 | 28.81 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 22 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002833.SZ | - | 17.55 | 18.67 | +6.38% | 17.03 | 18.39 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 23 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002919.SZ | - | 20.20 | 20.06 | -0.69% | 19.64 | 21.04 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 24 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002929.SZ | - | 59.89 | 65.10 | +8.70% | 57.96 | 62.82 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 25 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002943.SZ | - | 51.33 | 52.43 | +2.14% | 49.43 | 54.54 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 26 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002948.SZ | - | 5.93 | 5.37 | -9.44% | 5.69 | 6.29 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 27 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 002952.SZ | - | 22.91 | 22.56 | -1.53% | 22.18 | 24.08 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 28 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300001.SZ | - | 36.80 | 39.08 | +6.20% | 35.67 | 38.71 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 29 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300012.SZ | - | 13.89 | 14.35 | +3.31% | 13.97 | 14.32 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 30 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300351.SZ | - | 16.11 | 17.46 | +8.38% | 15.68 | 16.78 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 31 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300395.SZ | - | 120.36 | 133.48 | +10.90% | 117.06 | 126.08 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 32 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300469.SZ | - | 52.00 | 53.84 | +3.54% | 49.71 | 55.61 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 33 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300473.SZ | - | 31.85 | 30.36 | -4.68% | 30.78 | 33.50 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 34 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300499.SZ | - | 34.71 | 42.47 | +22.36% | 33.11 | 37.12 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 35 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300782.SZ | - | 93.56 | 113.63 | +21.45% | 90.13 | 99.98 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 36 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300823.SZ | - | 15.88 | 15.32 | -3.53% | 15.44 | 16.56 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 37 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300849.SZ | - | 22.53 | 23.38 | +3.77% | 21.75 | 23.74 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 38 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300860.SZ | - | 25.77 | 25.95 | +0.70% | 25.03 | 26.90 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 39 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 300921.SZ | - | 17.60 | 21.69 | +23.24% | 16.95 | 18.62 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 40 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301046.SZ | - | 25.79 | 26.80 | +3.92% | 24.55 | 27.68 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 41 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301070.SZ | - | 97.74 | 86.93 | -11.06% | 93.83 | 103.83 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 42 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301141.SZ | - | 47.98 | 46.30 | -3.50% | 46.72 | 50.24 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 43 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301171.SZ | - | 37.25 | 36.13 | -3.01% | 36.27 | 39.22 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 44 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301191.SZ | - | 94.06 | 106.89 | +13.64% | 91.14 | 99.21 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 45 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301232.SZ | - | 115.67 | 145.13 | +25.47% | 112.32 | 120.83 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 46 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301260.SZ | - | 15.24 | 14.40 | -5.51% | 14.59 | 16.22 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 47 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301421.SZ | - | 87.61 | 91.92 | +4.92% | 84.88 | 91.74 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 48 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301479.SZ | - | 61.92 | 62.04 | +0.19% | 60.10 | 64.78 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 49 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 301548.SZ | - | 71.11 | 95.25 | +33.95% | 68.97 | 74.67 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 50 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600020.SH | - | 3.99 | 3.81 | -4.51% | 3.86 | 4.19 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 51 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600207.SH | - | 6.50 | 5.77 | -11.23% | 6.26 | 6.92 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 52 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600336.SH | - | 7.05 | 6.34 | -10.07% | 6.85 | 7.38 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 53 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600502.SH | - | 4.74 | 4.53 | -4.43% | 4.58 | 4.99 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 54 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600525.SH | - | 4.95 | 4.90 | -1.01% | 4.78 | 5.22 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 55 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600527.SH | - | 2.30 | 2.27 | -1.30% | 2.23 | 2.41 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 56 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600568.SH | - | 2.59 | 2.15 | -16.99% | 2.48 | 2.76 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 57 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600575.SH | - | 3.63 | 3.40 | -6.34% | 3.49 | 3.84 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 58 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600850.SH | - | 18.69 | 18.71 | +0.11% | 18.15 | 19.52 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 59 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 600857.SH | - | 14.00 | 15.78 | +12.71% | 13.46 | 14.84 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 60 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 601077.SH | - | 7.04 | 6.36 | -9.66% | 6.84 | 7.35 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 61 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 601233.SH | - | 21.57 | 24.25 | +12.42% | 20.58 | 23.37 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 62 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 601577.SH | - | 9.70 | 9.08 | -6.39% | 9.32 | 10.27 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 63 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 601816.SH | - | 5.02 | 4.54 | -9.56% | 4.85 | 5.28 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 64 | [已持仓] | 20260610 | 20260610 | 601919.SH | - | 14.49 | 14.00 | -3.38% | 13.99 | 15.26 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 65 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603048.SH | - | 19.20 | 18.86 | -1.77% | 18.41 | 20.42 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 66 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603093.SH | - | 18.10 | 20.72 | +14.48% | 17.26 | 19.37 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 67 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603159.SH | - | 27.23 | 21.06 | -22.66% | 25.97 | 29.24 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 68 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603228.SH | - | 75.25 | 72.90 | -3.12% | 72.48 | 79.85 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 69 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603255.SH | - | 30.08 | 34.18 | +13.63% | 29.11 | 31.58 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 70 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603368.SH | - | 16.33 | 15.46 | -5.33% | 15.60 | 17.43 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 71 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603383.SH | - | 28.87 | 28.65 | -0.76% | 27.85 | 30.78 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 72 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603586.SH | - | 18.06 | 13.38 | -25.91% | 17.55 | 18.83 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 73 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603637.SH | - | 18.00 | 19.20 | +6.67% | 17.21 | 19.58 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 74 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603906.SH | - | 23.34 | 29.10 | +24.68% | 22.63 | 24.65 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 75 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 603937.SH | - | 13.36 | 13.79 | +3.22% | 12.96 | 14.01 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 76 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 605016.SH | - | 24.40 | 25.26 | +3.52% | 23.77 | 25.43 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 77 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 605218.SH | - | 16.87 | 17.06 | +1.13% | 16.22 | 17.94 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 78 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688006.SH | - | 33.74 | 39.79 | +17.93% | 32.08 | 36.36 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 79 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688102.SH | - | 36.42 | 43.10 | +18.34% | 34.96 | 38.66 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 80 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688109.SH | - | 79.24 | 79.90 | +0.83% | 76.67 | 83.11 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 81 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688305.SH | - | 65.80 | 66.21 | +0.62% | 62.77 | 71.03 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 82 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688391.SH | - | 29.31 | 34.71 | +18.42% | 28.43 | 30.66 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 83 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688411.SH | - | 240.00 | 266.19 | +10.91% | 233.26 | 250.43 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 84 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688419.SH | - | 45.93 | 74.69 | +62.62% | 44.03 | 48.84 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 85 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688480.SH | - | 88.16 | 95.59 | +8.43% | 84.07 | 94.32 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 86 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688515.SH | - | 190.00 | 266.63 | +40.33% | 181.26 | 206.55 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 87 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688521.SH | - | 228.11 | 300.90 | +31.91% | 221.36 | 239.07 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 88 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688577.SH | - | 45.31 | 47.20 | +4.17% | 44.09 | 47.41 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 89 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688593.SH | - | 30.35 | 35.78 | +17.89% | 29.04 | 32.32 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 90 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688618.SH | - | 31.51 | 32.53 | +3.24% | 30.62 | 32.86 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 91 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688629.SH | - | 138.60 | 148.91 | +7.44% | 134.82 | 144.63 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 92 | [已持仓] | 20260610 | 2026-06-10T15:23:13 | 688633.SH | - | 28.75 | 31.53 | +9.67% | 27.70 | 30.63 | OPEN | OB_Bull/BOS_Bull | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 93 | [已持仓] | 20260611 | 20260611 | 000759.SZ | - | 5.29 | 6.18 | +16.82% | 4.70 | 6.19 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 94 | [已持仓] | 20260611 | 20260611 | 000767.SZ | - | 4.63 | 4.15 | -10.37% | 4.04 | 5.67 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 95 | [已持仓] | 20260611 | 20260611 | 001301.SZ | - | 83.50 | 93.45 | +11.92% | 74.66 | 96.77 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 96 | [已持仓] | 20260611 | 20260611 | 002350.SZ | - | 14.31 | 14.17 | -0.98% | 12.87 | 16.63 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 97 | [已持仓] | 20260611 | 20260611 | 002789.SZ | - | 13.12 | 12.75 | -2.82% | 12.07 | 14.73 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 98 | [已持仓] | 20260611 | 20260611 | 300088.SZ | - | 8.00 | 9.81 | +22.63% | 7.03 | 9.46 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 99 | [已持仓] | 20260611 | 20260611 | 300410.SZ | - | 11.06 | 12.17 | +10.04% | 9.86 | 12.87 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 100 | [已持仓] | 20260611 | 20260611 | 300472.SZ | - | 7.90 | 7.69 | -2.66% | 7.47 | 8.58 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 101 | [已持仓] | 20260611 | 20260611 | 300476.SZ | - | 340.06 | 343.43 | +0.99% | 300.48 | 399.68 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 102 | [已持仓] | 20260611 | 20260611 | 300593.SZ | - | 35.56 | 33.19 | -6.66% | 31.56 | 42.82 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 103 | [已持仓] | 20260611 | 20260611 | 301002.SZ | - | 44.18 | 41.41 | -6.27% | 39.32 | 51.87 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 104 | [已持仓] | 20260611 | 20260611 | 301133.SZ | - | 40.45 | 39.83 | -1.53% | 36.69 | 46.45 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 105 | [已持仓] | 20260611 | 20260611 | 600575.SH | - | 3.77 | 3.40 | -9.81% | 3.42 | 4.30 | OPEN | OB_Bull/CHOCH_Bull | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 106 | [已持仓] | 20260611 | 20260611 | 601088.SH | - | 46.99 | 40.05 | -14.77% | 45.80 | 49.02 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 107 | [已持仓] | 20260611 | 20260611 | 601588.SH | - | 1.91 | 1.71 | -10.47% | 1.73 | 2.20 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 108 | [已持仓] | 20260611 | 20260611 | 601677.SH | - | 16.80 | 17.01 | +1.25% | 15.47 | 18.92 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 109 | [已持仓] | 20260611 | 20260611 | 603001.SH | - | 9.77 | 14.14 | +44.73% | 8.73 | 11.34 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 110 | [已持仓] | 20260611 | 20260611 | 603070.SH | - | 14.38 | 14.04 | -2.36% | 12.39 | 17.36 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 111 | [已持仓] | 20260611 | 20260611 | 603159.SH | - | 26.50 | 21.06 | -20.53% | 24.94 | 29.10 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 112 | [已持仓] | 20260611 | 20260611 | 603838.SH | - | 8.70 | 9.43 | +8.39% | 8.28 | 9.35 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 113 | [已持仓] | 20260611 | 20260611 | 605336.SH | - | 16.23 | 15.51 | -4.44% | 15.23 | 17.75 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 114 | [已持仓] | 20260611 | 20260611 | 688135.SH | - | 35.57 | 40.39 | +13.55% | 29.80 | 44.42 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 115 | [已持仓] | 20260611 | 20260611 | 688187.SH | - | 55.95 | 61.27 | +9.51% | 48.17 | 67.73 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 116 | [已持仓] | 20260611 | 20260611 | 688484.SH | - | 42.00 | 54.25 | +29.17% | 37.92 | 48.38 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 117 | [已持仓] | 20260611 | 20260611 | 688612.SH | - | 31.81 | 29.43 | -7.48% | 28.83 | 36.89 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 118 | [已持仓] | 20260611 | 20260611 | 688679.SH | - | 54.00 | 46.62 | -13.67% | 47.58 | 64.66 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 119 | [已持仓] | 20260612 | 20260612 | 000767.SZ | - | 4.65 | 4.15 | -10.75% | 3.98 | 5.97 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 120 | [已持仓] | 20260612 | 20260612 | 002876.SZ | - | 30.01 | 35.26 | +17.49% | 27.84 | 33.61 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 121 | [已持仓] | 20260612 | 20260612 | 300475.SZ | - | 193.00 | 289.60 | +50.05% | 173.93 | 221.62 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 122 | [已持仓] | 20260612 | 20260612 | 301002.SZ | - | 42.15 | 41.41 | -1.76% | 38.56 | 47.58 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 123 | [已持仓] | 20260612 | 20260612 | 301029.SZ | - | 29.17 | 29.25 | +0.27% | 27.51 | 31.76 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 124 | [已持仓] | 20260612 | 20260612 | 301133.SZ | - | 40.18 | 39.83 | -0.87% | 35.35 | 47.45 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 125 | [已持仓] | 20260612 | 20260612 | 301317.SZ | - | 57.00 | 64.63 | +13.39% | 51.66 | 65.34 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 126 | [已持仓] | 20260612 | 20260612 | 603001.SH | - | 9.63 | 14.14 | +46.83% | 8.68 | 11.11 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 127 | [已持仓] | 20260612 | 20260612 | 688135.SH | - | 34.36 | 40.39 | +17.55% | 28.73 | 42.82 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 128 | [已持仓] | 20260612 | 20260612 | 688392.SH | - | 153.67 | 175.20 | +14.01% | 136.21 | 179.85 | OPEN | FVG_Bull/BOS_Bull | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 129 | [已持仓] | 20260612 | 20260612 | 688612.SH | - | 31.15 | 29.43 | -5.52% | 28.59 | 35.14 | OPEN | FVG_Bull/CHOCH_Bull | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |

## 每日活跃选股明细（26 条，全部列出）
| # | 标记 | 选股日 | 入场日 | 代码 | 名称 | 入场/成本 | 当前价 | PnL | SL | TP | live状态 | pick状态 | scope | 信号类型 | BQ/Score |
|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---:|
| 1 | [已持仓] | 20260617 | 20260617 | 688327.SH | - | 13.82 | 13.65 | -1.23% | 12.83 | 15.30 | NO_LIVE_LAST_PRICE | ACTIVE_BUY_VALID | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 2 | [已持仓] | 20260616 | 20260616 | 300757.SZ | - | 630.32 | 602.50 | +0.00% | 592.23 | 687.46 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 3 | [已持仓] | 20260616 | 20260616 | 688048.SH | - | 360.95 | 420.00 | +0.00% | 325.57 | 414.02 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 4 | [已持仓] | 20260616 | 20260616 | 688376.SH | - | 78.05 | 84.60 | +0.00% | 70.69 | 89.10 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 5 | [已持仓] | 20260616 | 20260616 | 688486.SH | - | 52.90 | 56.60 | +0.00% | 49.45 | 58.07 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 6 | [已持仓] | 20260615 | 20260615 | 000567.SZ | - | 5.68 | 5.96 | +0.00% | 5.40 | 6.11 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 7 | [已持仓] | 20260615 | 20260615 | 002401.SZ | - | 12.70 | 12.39 | +0.00% | 12.04 | 13.69 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 8 | [已持仓] | 20260615 | 20260615 | 688277.SH | - | 17.54 | 19.13 | +0.00% | 16.14 | 19.64 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 9 | [已持仓] | 20260612 | 20260612 | 300568.SZ | - | 17.46 | 18.30 | +0.00% | 16.64 | 18.69 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 10 | [已持仓] | 20260612 | 20260612 | 600259.SH | - | 93.99 | 104.77 | +0.00% | 85.90 | 106.12 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 11 | [已持仓] | 20260611 | 20260611 | 002850.SZ | - | 187.42 | 186.59 | -0.44% | 174.35 | 207.03 | NO_LIVE_LAST_PRICE | ACTIVE_BUY_VALID | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 12 | [已持仓] | 20260611 | 20260611 | 603568.SH | - | 15.71 | 16.00 | +0.00% | 14.93 | 16.88 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 13 | [已持仓] | 20260611 | 20260611 | 688156.SH | - | 25.29 | 26.70 | +0.00% | 23.87 | 27.42 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 14 | [已持仓] | 20260610 | 20260610 | 002368.SZ | - | 15.54 | 16.28 | +0.00% | 14.96 | 16.41 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 15 | [已持仓] | 20260610 | 20260610 | 002643.SZ | - | 14.03 | 19.51 | +0.00% | 13.32 | 15.08 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 16 | [已持仓] | 20260610 | 20260610 | 002937.SZ | - | 35.00 | 43.13 | +0.00% | 32.75 | 38.38 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 17 | [已持仓] | 20260610 | 20260610 | 300637.SZ | - | 9.91 | 11.00 | +0.00% | 9.38 | 10.71 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 18 | [已持仓] | 20260610 | 20260610 | 600392.SH | - | 23.42 | 31.60 | +0.00% | 22.01 | 25.54 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 19 | [已持仓] | 20260610 | 20260610 | 603072.SH | - | 35.86 | 38.63 | +0.00% | 34.25 | 38.27 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 20 | [已持仓] | 20260610 | 20260610 | 688035.SH | - | 77.00 | 96.28 | +0.00% | 71.78 | 84.84 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 21 | [已持仓] | 20260610 | 20260610 | 688138.SH | - | 32.07 | 40.14 | +0.00% | 29.99 | 35.19 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 22 | [已持仓] | 20260610 | 20260610 | 688721.SH | - | 41.48 | 53.65 | +0.00% | 38.87 | 45.40 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 23 | [已持仓] | 20260609 | 20260609 | 603638.SH | - | 23.35 | 23.54 | +0.81% | 21.42 | 26.24 | NO_LIVE_LAST_PRICE | ACTIVE_BUY_VALID | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 24 | [已持仓] | 20260608 | 20260608 | 002631.SZ | - | 7.20 | 9.89 | +0.00% | 6.66 | 8.01 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 25 | [已持仓] | 20260605 | 20260605 | 603161.SH | - | 14.69 | 14.68 | -0.05% | 13.63 | 16.28 | NO_LIVE_LAST_PRICE | ACTIVE_BUY_VALID | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |
| 26 | [已持仓] | 20260529 | 20260529 | 000630.SZ | - | 6.81 | 6.94 | +0.00% | 6.32 | 7.55 | NON_TRADABLE_CONTEXT | WATCH_ONLY_CONTEXT | ACTIVE_CANDIDATE | OB_Bull/TRUE_TAKEOVER_3_STRICT | - |

## 失败 / 风险
- 已确认原始 wrapper 超时：`Script timed out after 120s: /root/.hermes/scripts/v25/smc_morning_push.py`。
- `smc_daily_ops.py` 实际继续运行到 08:49 后完成；因此该 120s 是早盘推送 wrapper/预检超时，不是日常 ops 未完成。
- K线刷新遥测出现较多失败：failed=1692，样例包括 `Expecting value: line 1 column 1` 和短历史 `rows=43`；已用缓存覆盖复核，当前有效覆盖 4637/4905。
- live-prices 当前提示：休市 (交易时间: 周一至周五 9:30-11:30, 13:00-15:00)；市场未开盘/无实时价时，应以最后K线价作展示，不代表全部可立即下单。
- 本次恢复报告未在当前 cron 上下文中直接调用外部 send_message；完整内容写入最终响应，并保存为本地报告文件。

_生成时间：2026-06-25 08:56:26_
