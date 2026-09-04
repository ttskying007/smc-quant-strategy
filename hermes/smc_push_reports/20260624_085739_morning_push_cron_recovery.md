# SMC morning push cron recovery report - 2026-06-24 08:57:39 CST

## Conclusion
- Morning push hit the 120s cron wrapper timeout. Recovery workflow was used; no duplicate unchanged morning push was started.
- smc_daily_ops.py was found still running in the background, so I waited for it to finish normally before final reporting.
- Frontend/API port 8890 responded successfully. This report is generated from the latest ops_latest.json and live APIs.

## Pipeline status
- ops_latest generated_at: 2026-06-24T08:51:43; data_date: 20260623; date: 20260624
- Kline refresh: requested=4905, ok=4655, failed=250, returncode=0, duration_sec=133.5
- Kline latest_counts: {'20260623': 4639, '20260413': 1, '20260527': 1, '20260622': 4, '20210528': 1, '20260430': 3, '20260616': 2, '20250812': 1, '20260615': 1, '20260608': 1, '20260611': 1}
- Kline top_errors: {'rows=1': 247, 'rows=42': 2, 'rows=0': 1}
- V90 selector: returncode=0, duration_sec=211.6, started=2026-06-24T08:32:26, finished=2026-06-24T08:35:57
- Shadow selector: returncode=0, duration_sec=945.1, started=2026-06-24T08:35:57, finished=2026-06-24T08:51:42
- API summary: version=V175, engine=V175_DEMAND_OB_TRUE_TAKEOVER_SEMANTIC_SPLIT, total_trades=247, win_rate=83.8, avg_pnl=6.05
- live-prices: total=26, tradableLiveCount=3, watchContextCount=23, market_open=False, error=休市 (交易时间: 周一至周五 9:30-11:30, 13:00-15:00), dataDate=20260623

## Counts
- Monitor positions: total=140, OPEN=129, dedup_OPEN=129, NEXT_DAY_PENDING=0, closed=9, watch_only=2
- /api/picks rows=26, production_active_picks=26, pick_scope_counts={'ACTIVE_CANDIDATE': 26}, state_status_counts={'ACTIVE_CANDIDATE': 26}
- /api/live-prices picks=26, tradable=3, watch_context=23, pickScope_counts={'ACTIVE_CANDIDATE': 26}, status_counts={'NO_LIVE_LAST_PRICE': 3, 'NON_TRADABLE_CONTEXT': 23}

## All OPEN holdings after dedupe
| # | pick_date | buy_or_fill_time | symbol | name | cost | current | pnl_pct | sl | tp | status | signal |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | 20260609 | 2026-06-10T09:30:02 | 601088.SH |  | 48.75 |  |  | 46.98 | 51.42 | OPEN | ->->OB_Bull->BOS_Bull |
| 2 | 20260609 | 2026-06-10T09:30:02 | 601398.SH |  | 7.57 |  |  | 7.18 | 8.04 | OPEN | ->->FVG_Bull->CHOCH_Bull |
| 3 | 20260609 | 2026-06-10T09:30:02 | 603060.SH |  | 7.16 |  |  | 6.84 | 7.65 | OPEN | ->->FVG_Bull->BOS_Bull |
| 4 | 20260610 | 2026-06-11T09:30:15 | 000001.SZ |  | 11.29 |  |  | 10.95 | 11.81 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 5 | 20260610 | 2026-06-11T09:30:05 | 000785.SZ |  | 2.35 |  |  | 2.29 | 2.46 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 6 | 20260610 | 2026-06-11T09:30:18 | 000929.SZ |  | 9.27 |  |  | 8.96 | 9.74 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 7 | 20260610 | 2026-06-11T09:30:19 | 000977.SZ |  | 59.18 |  |  | 57.46 | 61.87 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 8 | 20260610 | 2026-06-11T09:30:16 | 002058.SZ |  | 22.76 |  |  | 21.75 | 24.31 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 9 | 20260610 | 2026-06-11T09:30:14 | 002108.SZ |  | 4.63 |  |  | 4.49 | 4.85 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 10 | 20260610 | 2026-06-11T09:30:08 | 002192.SZ |  | 79.19 |  |  | 77.17 | 82.80 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 11 | 20260610 | 2026-06-11T09:30:10 | 002210.SZ |  | 2.56 |  |  | 2.45 | 2.73 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 12 | 20260610 | 2026-06-11T09:30:20 | 002297.SZ |  | 21.18 |  |  | 20.31 | 22.70 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 13 | 20260610 | 2026-06-11T09:30:06 | 002331.SZ |  | 8.31 |  |  | 7.97 | 8.82 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 14 | 20260610 | 2026-06-11T09:30:21 | 002335.SZ |  | 36.65 |  |  | 35.58 | 38.30 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 15 | 20260610 | 2026-06-11T09:30:24 | 002415.SZ |  | 30.21 |  |  | 29.39 | 31.50 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 16 | 20260610 | 2026-06-11T09:30:07 | 002512.SZ |  | 4.09 |  |  | 3.94 | 4.33 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 17 | 20260610 | 2026-06-11T09:30:21 | 002515.SZ |  | 7.39 |  |  | 7.13 | 7.81 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 18 | 20260610 | 2026-06-11T09:30:16 | 002606.SZ |  | 13.58 |  |  | 13.06 | 14.44 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 19 | 20260610 | 2026-06-11T09:30:07 | 002637.SZ |  | 11.46 |  |  | 10.99 | 12.16 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 20 | 20260610 | 2026-06-11T09:30:19 | 002678.SZ |  | 5.59 |  |  | 5.42 | 5.86 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 21 | 20260610 | 2026-06-11T09:30:17 | 002824.SZ |  | 27.28 |  |  | 26.30 | 28.81 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 22 | 20260610 | 2026-06-11T09:30:14 | 002833.SZ |  | 17.55 |  |  | 17.03 | 18.39 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 23 | 20260610 | 2026-06-11T09:30:14 | 002919.SZ |  | 20.20 |  |  | 19.64 | 21.04 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 24 | 20260610 | 2026-06-11T09:30:12 | 002929.SZ |  | 59.89 |  |  | 57.96 | 62.82 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 25 | 20260610 | 2026-06-11T09:30:16 | 002943.SZ |  | 51.33 |  |  | 49.43 | 54.54 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 26 | 20260610 | 2026-06-11T09:30:06 | 002948.SZ |  | 5.93 |  |  | 5.69 | 6.29 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 27 | 20260610 | 2026-06-11T09:30:15 | 002952.SZ |  | 22.91 |  |  | 22.18 | 24.08 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 28 | 20260610 | 2026-06-11T09:30:06 | 300001.SZ |  | 36.80 |  |  | 35.67 | 38.71 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 29 | 20260610 | 2026-06-11T09:30:09 | 300012.SZ |  | 13.89 |  |  | 13.97 | 14.32 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 30 | 20260610 | 2026-06-11T09:30:09 | 300351.SZ |  | 16.11 |  |  | 15.68 | 16.78 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 31 | 20260610 | 2026-06-11T09:30:17 | 300395.SZ |  | 120.36 |  |  | 117.06 | 126.08 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 32 | 20260610 | 2026-06-11T09:30:19 | 300469.SZ |  | 52.00 |  |  | 49.71 | 55.61 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 33 | 20260610 | 2026-06-11T09:30:11 | 300473.SZ |  | 31.85 |  |  | 30.78 | 33.50 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 34 | 20260610 | 2026-06-11T09:30:08 | 300499.SZ |  | 34.71 |  |  | 33.11 | 37.12 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 35 | 20260610 | 2026-06-11T09:30:12 | 300782.SZ |  | 93.56 |  |  | 90.13 | 99.98 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 36 | 20260610 | 2026-06-11T09:30:14 | 300823.SZ |  | 15.88 |  |  | 15.44 | 16.56 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 37 | 20260610 | 2026-06-11T09:30:15 | 300849.SZ |  | 22.53 |  |  | 21.75 | 23.74 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 38 | 20260610 | 2026-06-11T09:30:18 | 300860.SZ |  | 25.77 |  |  | 25.03 | 26.90 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 39 | 20260610 | 2026-06-11T09:30:17 | 300921.SZ |  | 17.60 |  |  | 16.95 | 18.62 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 40 | 20260610 | 2026-06-11T09:30:22 | 301046.SZ |  | 25.79 |  |  | 24.55 | 27.68 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 41 | 20260610 | 2026-06-11T09:30:20 | 301070.SZ |  | 97.74 |  |  | 93.83 | 103.83 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 42 | 20260610 | 2026-06-11T09:30:14 | 301141.SZ |  | 47.98 |  |  | 46.72 | 50.24 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 43 | 20260610 | 2026-06-11T09:30:13 | 301171.SZ |  | 37.25 |  |  | 36.27 | 39.22 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 44 | 20260610 | 2026-06-11T09:30:08 | 301191.SZ |  | 94.06 |  |  | 91.14 | 99.21 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 45 | 20260610 | 2026-06-11T09:30:18 | 301232.SZ |  | 115.67 |  |  | 112.32 | 120.83 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 46 | 20260610 | 2026-06-11T09:30:14 | 301260.SZ |  | 15.24 |  |  | 14.59 | 16.22 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 47 | 20260610 | 2026-06-11T09:30:22 | 301421.SZ |  | 87.61 |  |  | 84.88 | 91.74 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 48 | 20260610 | 2026-06-11T09:30:11 | 301479.SZ |  | 61.92 |  |  | 60.10 | 64.78 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 49 | 20260610 | 2026-06-11T09:30:22 | 301548.SZ |  | 71.11 |  |  | 68.97 | 74.67 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 50 | 20260610 | 2026-06-11T09:30:15 | 600020.SH |  | 3.99 |  |  | 3.86 | 4.19 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 51 | 20260610 | 2026-06-11T09:30:05 | 600207.SH |  | 6.50 |  |  | 6.26 | 6.92 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 52 | 20260610 | 2026-06-11T09:30:24 | 600336.SH |  | 7.05 |  |  | 6.85 | 7.38 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 53 | 20260610 | 2026-06-11T09:30:24 | 600502.SH |  | 4.74 |  |  | 4.58 | 4.99 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 54 | 20260610 | 2026-06-11T09:30:17 | 600525.SH |  | 4.95 |  |  | 4.78 | 5.22 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 55 | 20260610 | 2026-06-11T09:30:21 | 600527.SH |  | 2.30 |  |  | 2.23 | 2.41 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 56 | 20260610 | 2026-06-11T09:30:19 | 600568.SH |  | 2.59 |  |  | 2.48 | 2.76 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 57 | 20260610 | 2026-06-11T09:30:16 | 600575.SH |  | 3.63 |  |  | 3.49 | 3.84 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 58 | 20260610 | 2026-06-11T09:30:12 | 600850.SH |  | 18.69 |  |  | 18.15 | 19.52 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 59 | 20260610 | 2026-06-11T09:30:12 | 600857.SH |  | 14.00 |  |  | 13.46 | 14.84 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 60 | 20260610 | 2026-06-11T09:30:13 | 601077.SH |  | 7.04 |  |  | 6.84 | 7.35 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 61 | 20260610 | 2026-06-11T09:30:15 | 601233.SH |  | 21.57 |  |  | 20.58 | 23.37 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 62 | 20260610 | 2026-06-11T09:30:18 | 601577.SH |  | 9.70 |  |  | 9.32 | 10.27 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 63 | 20260610 | 2026-06-11T09:30:20 | 601816.SH |  | 5.02 |  |  | 4.85 | 5.28 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 64 | 20260610 | 2026-06-11T09:30:25 | 601919.SH |  | 14.49 |  |  | 13.99 | 15.26 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 65 | 20260610 | 2026-06-11T09:30:11 | 603048.SH |  | 19.20 |  |  | 18.41 | 20.42 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 66 | 20260610 | 2026-06-11T09:30:12 | 603093.SH |  | 18.10 |  |  | 17.26 | 19.37 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 67 | 20260610 | 2026-06-11T09:30:13 | 603159.SH |  | 27.23 |  |  | 25.97 | 29.24 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 68 | 20260610 | 2026-06-11T09:30:12 | 603228.SH |  | 75.25 |  |  | 72.48 | 79.85 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 69 | 20260610 | 2026-06-11T09:30:14 | 603255.SH |  | 30.08 |  |  | 29.11 | 31.58 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 70 | 20260610 | 2026-06-11T09:30:23 | 603368.SH |  | 16.33 |  |  | 15.60 | 17.43 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 71 | 20260610 | 2026-06-11T09:30:19 | 603383.SH |  | 28.87 |  |  | 27.85 | 30.78 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 72 | 20260610 | 2026-06-11T09:30:19 | 603586.SH |  | 18.06 |  |  | 17.55 | 18.83 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 73 | 20260610 | 2026-06-11T09:30:21 | 603637.SH |  | 18.00 |  |  | 17.21 | 19.58 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 74 | 20260610 | 2026-06-11T09:30:18 | 603906.SH |  | 23.34 |  |  | 22.63 | 24.65 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 75 | 20260610 | 2026-06-11T09:30:13 | 603937.SH |  | 13.36 |  |  | 12.96 | 14.01 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 76 | 20260610 | 2026-06-11T09:30:04 | 605016.SH |  | 24.40 |  |  | 23.77 | 25.43 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 77 | 20260610 | 2026-06-11T09:30:05 | 605218.SH |  | 16.87 |  |  | 16.22 | 17.94 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 78 | 20260610 | 2026-06-11T09:30:20 | 688006.SH |  | 33.74 |  |  | 32.08 | 36.36 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 79 | 20260610 | 2026-06-11T09:30:19 | 688102.SH |  | 36.42 |  |  | 34.96 | 38.66 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 80 | 20260610 | 2026-06-11T09:30:18 | 688109.SH |  | 79.24 |  |  | 76.67 | 83.11 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 81 | 20260610 | 2026-06-11T09:30:07 | 688305.SH |  | 65.80 |  |  | 62.77 | 71.03 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 82 | 20260610 | 2026-06-11T09:30:13 | 688391.SH |  | 29.31 |  |  | 28.43 | 30.66 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 83 | 20260610 | 2026-06-11T09:30:10 | 688411.SH |  | 240.00 |  |  | 233.26 | 250.43 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 84 | 20260610 | 2026-06-11T09:30:21 | 688419.SH |  | 45.93 |  |  | 44.03 | 48.84 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 85 | 20260610 | 2026-06-11T09:30:17 | 688480.SH |  | 88.16 |  |  | 84.07 | 94.32 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 86 | 20260610 | 2026-06-11T09:30:16 | 688515.SH |  | 190.00 |  |  | 181.26 | 206.55 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 87 | 20260610 | 2026-06-11T09:30:19 | 688521.SH |  | 228.11 |  |  | 221.36 | 239.07 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 88 | 20260610 | 2026-06-11T09:30:21 | 688577.SH |  | 45.31 |  |  | 44.09 | 47.41 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 89 | 20260610 | 2026-06-11T09:30:16 | 688593.SH |  | 30.35 |  |  | 29.04 | 32.32 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 90 | 20260610 | 2026-06-11T09:30:23 | 688618.SH |  | 31.51 |  |  | 30.62 | 32.86 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 91 | 20260610 | 2026-06-11T09:30:16 | 688629.SH |  | 138.60 |  |  | 134.82 | 144.63 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 92 | 20260610 | 2026-06-11T09:30:22 | 688633.SH |  | 28.75 |  |  | 27.70 | 30.63 | OPEN | ->->OB_Bull->BOS_Bull->RETRACE_ENTRY |
| 93 | 20260611 | 2026-06-12T09:30:04 | 000759.SZ |  | 5.29 |  |  | 4.70 | 6.19 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 94 | 20260611 | 2026-06-12T09:30:02 | 000767.SZ |  | 4.63 |  |  | 4.04 | 5.67 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 95 | 20260611 | 2026-06-12T09:30:03 | 001301.SZ |  | 83.50 |  |  | 74.66 | 96.77 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 96 | 20260611 | 2026-06-12T09:30:02 | 002350.SZ |  | 14.31 |  |  | 12.87 | 16.63 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 97 | 20260611 | 2026-06-12T09:30:03 | 002789.SZ |  | 13.12 |  |  | 12.07 | 14.73 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 98 | 20260611 | 2026-06-12T09:30:04 | 300088.SZ |  | 8.00 |  |  | 7.03 | 9.46 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 99 | 20260611 | 2026-06-12T09:30:02 | 300410.SZ |  | 11.06 |  |  | 9.86 | 12.87 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 100 | 20260611 | 2026-06-12T09:30:02 | 300472.SZ |  | 7.90 |  |  | 7.47 | 8.58 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 101 | 20260611 | 2026-06-12T09:30:03 | 300476.SZ |  | 340.06 |  |  | 300.48 | 399.68 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 102 | 20260611 | 2026-06-12T09:30:03 | 300593.SZ |  | 35.56 |  |  | 31.56 | 42.82 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 103 | 20260611 | 2026-06-12T09:30:04 | 301002.SZ |  | 44.18 |  |  | 39.32 | 51.87 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 104 | 20260611 | 2026-06-12T09:30:03 | 301133.SZ |  | 40.45 |  |  | 36.69 | 46.45 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 105 | 20260611 | 2026-06-12T09:30:02 | 600575.SH |  | 3.77 |  |  | 3.42 | 4.30 | OPEN | ->->OB_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 106 | 20260611 | 2026-06-12T09:30:04 | 601088.SH |  | 46.99 |  |  | 45.80 | 49.02 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 107 | 20260611 | 2026-06-12T09:30:03 | 601588.SH |  | 1.91 |  |  | 1.73 | 2.20 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 108 | 20260611 | 2026-06-12T09:30:04 | 601677.SH |  | 16.80 |  |  | 15.47 | 18.92 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 109 | 20260611 | 2026-06-12T09:30:03 | 603001.SH |  | 9.77 |  |  | 8.73 | 11.34 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 110 | 20260611 | 2026-06-12T09:30:04 | 603070.SH |  | 14.38 |  |  | 12.39 | 17.36 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 111 | 20260611 | 2026-06-12T09:30:04 | 603159.SH |  | 26.50 |  |  | 24.94 | 29.10 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 112 | 20260611 | 2026-06-12T09:30:04 | 603838.SH |  | 8.70 |  |  | 8.28 | 9.35 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 113 | 20260611 | 2026-06-12T09:30:03 | 605336.SH |  | 16.23 |  |  | 15.23 | 17.75 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 114 | 20260611 | 2026-06-12T09:30:04 | 688135.SH |  | 35.57 |  |  | 29.80 | 44.42 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 115 | 20260611 | 2026-06-12T09:30:02 | 688187.SH |  | 55.95 |  |  | 48.17 | 67.73 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 116 | 20260611 | 2026-06-12T09:30:04 | 688484.SH |  | 42.00 |  |  | 37.92 | 48.38 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 117 | 20260611 | 2026-06-12T09:30:04 | 688612.SH |  | 31.81 |  |  | 28.83 | 36.89 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 118 | 20260611 | 2026-06-12T09:30:03 | 688679.SH |  | 54.00 |  |  | 47.58 | 64.66 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 119 | 20260612 | 2026-06-15T09:30:02 | 000767.SZ |  | 4.65 |  |  | 3.98 | 5.97 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 120 | 20260612 | 2026-06-15T09:30:02 | 002876.SZ |  | 30.01 |  |  | 27.84 | 33.61 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 121 | 20260612 | 2026-06-15T09:30:03 | 300475.SZ |  | 193.00 |  |  | 173.93 | 221.62 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 122 | 20260612 | 2026-06-15T09:30:04 | 301002.SZ |  | 42.15 |  |  | 38.56 | 47.58 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 123 | 20260612 | 2026-06-15T09:30:03 | 301029.SZ |  | 29.17 |  |  | 27.51 | 31.76 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |
| 124 | 20260612 | 2026-06-15T09:30:04 | 301133.SZ |  | 40.18 |  |  | 35.35 | 47.45 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 125 | 20260612 | 2026-06-15T09:30:03 | 301317.SZ |  | 57.00 |  |  | 51.66 | 65.34 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 126 | 20260612 | 2026-06-15T09:30:03 | 603001.SH |  | 9.63 |  |  | 8.68 | 11.11 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 127 | 20260612 | 2026-06-15T09:30:04 | 688135.SH |  | 34.36 |  |  | 28.73 | 42.82 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 128 | 20260612 | 2026-06-15T09:30:03 | 688392.SH |  | 153.67 |  |  | 136.21 | 179.85 | OPEN | ->->FVG_Bull->BOS_Bull->RETRACE_ENTRY |
| 129 | 20260612 | 2026-06-15T09:30:02 | 688612.SH |  | 31.15 |  |  | 28.59 | 35.14 | OPEN | ->->FVG_Bull->CHOCH_Bull->RETRACE_ENTRY |

## All production active picks from /api/picks
| # | live_status | pick_date | entry_date | symbol | name | cost | current | pnl_pct | sl | tp | scope | tradable | signal | bq_or_rr |
|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|---:|
| 1 | NO_LIVE_LAST_PRICE | 20260617 | 20260617 | 688327.SH |  | 13.82 | 13.82 | 0.00 | 12.83 | 15.30 | ACTIVE_CANDIDATE | True | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 2 | NON_TRADABLE_CONTEXT | 20260616 | 20260616 | 300757.SZ |  | 630.32 | 578.20 | 0.00 | 592.23 | 687.46 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 3 | NON_TRADABLE_CONTEXT | 20260616 | 20260616 | 688048.SH |  | 360.95 | 392.05 | 0.00 | 325.57 | 414.02 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 4 | NON_TRADABLE_CONTEXT | 20260616 | 20260616 | 688376.SH |  | 78.05 | 79.66 | 0.00 | 70.69 | 89.10 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 5 | NON_TRADABLE_CONTEXT | 20260616 | 20260616 | 688486.SH |  | 52.90 | 57.00 | 0.00 | 49.45 | 58.07 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 6 | NON_TRADABLE_CONTEXT | 20260615 | 20260615 | 000567.SZ |  | 5.68 | 6.17 | 0.00 | 5.40 | 6.11 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 7 | NO_LIVE_LAST_PRICE | 20260615 | 20260615 | 002401.SZ |  | 12.70 | 12.81 | 0.87 | 12.04 | 13.69 | ACTIVE_CANDIDATE | True | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 8 | NON_TRADABLE_CONTEXT | 20260615 | 20260615 | 688277.SH |  | 17.54 | 19.15 | 0.00 | 16.14 | 19.64 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 9 | NON_TRADABLE_CONTEXT | 20260612 | 20260612 | 300568.SZ |  | 17.46 | 18.94 | 0.00 | 16.64 | 18.69 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 10 | NON_TRADABLE_CONTEXT | 20260612 | 20260612 | 600259.SH |  | 93.99 | 106.79 | 0.00 | 85.90 | 106.12 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 11 | NON_TRADABLE_CONTEXT | 20260611 | 20260611 | 002850.SZ |  | 187.42 | 184.58 | 0.00 | 174.35 | 207.03 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 12 | NO_LIVE_LAST_PRICE | 20260611 | 20260611 | 603568.SH |  | 15.71 | 15.50 | -1.34 | 14.93 | 16.88 | ACTIVE_CANDIDATE | True | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 13 | NON_TRADABLE_CONTEXT | 20260611 | 20260611 | 688156.SH |  | 25.29 | 27.66 | 0.00 | 23.87 | 27.42 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 14 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 002368.SZ |  | 15.54 | 16.73 | 0.00 | 14.96 | 16.41 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 15 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 002643.SZ |  | 14.03 | 17.74 | 0.00 | 13.32 | 15.08 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 16 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 002937.SZ |  | 35.00 | 41.80 | 0.00 | 32.75 | 38.38 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 17 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 300637.SZ |  | 9.91 | 10.57 | 0.00 | 9.38 | 10.71 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 18 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 600392.SH |  | 23.42 | 31.03 | 0.00 | 22.01 | 25.54 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 19 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 603072.SH |  | 35.86 | 40.00 | 0.00 | 34.25 | 38.27 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 20 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 688035.SH |  | 77.00 | 95.06 | 0.00 | 71.78 | 84.84 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 21 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 688138.SH |  | 32.07 | 38.22 | 0.00 | 29.99 | 35.19 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 22 | NON_TRADABLE_CONTEXT | 20260610 | 20260610 | 688721.SH |  | 41.48 | 52.19 | 0.00 | 38.87 | 45.40 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 23 | NON_TRADABLE_CONTEXT | 20260609 | 20260609 | 603638.SH |  | 23.35 | 23.97 | 0.00 | 21.42 | 26.24 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 24 | NON_TRADABLE_CONTEXT | 20260608 | 20260608 | 002631.SZ |  | 7.20 | 8.99 | 0.00 | 6.66 | 8.01 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 25 | NON_TRADABLE_CONTEXT | 20260605 | 20260605 | 603161.SH |  | 14.69 | 15.54 | 0.00 | 13.63 | 16.28 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |
| 26 | NON_TRADABLE_CONTEXT | 20260529 | 20260529 | 000630.SZ |  | 6.81 | 7.14 | 0.00 | 6.32 | 7.55 | ACTIVE_CANDIDATE | False | ->->OB_Bull->TRUE_TAKEOVER_3_STRICT | 1.50 |

## Risks and notes
- Kline refresh still has failures: failed=250; top_errors={'rows=1': 247, 'rows=42': 2, 'rows=0': 1}; latest 20260623 coverage=4639.
- Market status: 休市 (交易时间: 周一至周五 9:30-11:30, 13:00-15:00); current prices use last-kline/off-session values where available.
- No send_message call was made; cron final response plus this local report are the delivery artifacts.

## Final process check
```
(no matching SMC child processes)
```