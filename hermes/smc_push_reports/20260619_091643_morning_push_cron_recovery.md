# SMC Morning Cron Recovery Report 2026-06-19 09:16

## Summary
- smc_morning_push.py failed in cron: timeout after 120s. Manual rerun also timed out after 600s.
- Evidence: smc_morning_push.py runs smc_daily_ops.py synchronously before printing the report; smc_daily_ops/closed-loop process was still alive during inspection.
- ops_latest: generated_at=2026-06-19T08:49:06, data_date=20260618.
- kline refresh: requested=4905, ok=2022, failed=2883, latest_20260618=2009.
- selector: returncode=0, duration_sec=245.8.
- monitor/API counts: OPEN=130, NEXT_DAY_PENDING=0, api_picks=49, production_active_picks=0.

## OPEN holdings - all
| # | pick | buy | symbol | name | cost | last | pnl | SL | TP1 | status | signal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 06-10 | 06-11 | 000001.SZ | - | 11.29 | - | - | 10.95 | 11.81 | OPEN | FVG_Bull CHOCH_Bull |
| 2 | 06-11 | 06-12 | 000759.SZ | - | 5.29 | - | - | 4.70 | 6.19 | OPEN | FVG_Bull CHOCH_Bull |
| 3 | 06-11 | 06-12 | 000767.SZ | - | 4.63 | - | - | 4.04 | 5.67 | OPEN | FVG_Bull BOS_Bull |
| 4 | 06-12 | 06-15 | 000767.SZ | - | 4.65 | - | - | 3.98 | 5.97 | OPEN | FVG_Bull BOS_Bull |
| 5 | 06-10 | 06-11 | 000785.SZ | - | 2.35 | - | - | 2.29 | 2.46 | OPEN | OB_Bull CHOCH_Bull |
| 6 | 06-10 | 06-11 | 000929.SZ | - | 9.27 | - | - | 8.96 | 9.74 | OPEN | OB_Bull CHOCH_Bull |
| 7 | 06-10 | 06-11 | 000977.SZ | - | 59.18 | - | - | 57.46 | 61.87 | OPEN | FVG_Bull CHOCH_Bull |
| 8 | 06-11 | 06-12 | 001301.SZ | - | 83.50 | - | - | 74.66 | 96.77 | OPEN | FVG_Bull CHOCH_Bull |
| 9 | 06-10 | 06-11 | 002058.SZ | - | 22.76 | - | - | 21.75 | 24.31 | OPEN | OB_Bull BOS_Bull |
| 10 | 06-10 | 06-11 | 002108.SZ | - | 4.63 | - | - | 4.49 | 4.85 | OPEN | FVG_Bull CHOCH_Bull |
| 11 | 06-10 | 06-11 | 002192.SZ | - | 79.19 | - | - | 77.17 | 82.80 | OPEN | OB_Bull BOS_Bull |
| 12 | 06-10 | 06-11 | 002210.SZ | - | 2.56 | - | - | 2.45 | 2.73 | OPEN | OB_Bull CHOCH_Bull |
| 13 | 06-10 | 06-11 | 002297.SZ | - | 21.18 | - | - | 20.31 | 22.70 | OPEN | OB_Bull BOS_Bull |
| 14 | 06-10 | 06-11 | 002331.SZ | - | 8.31 | - | - | 7.97 | 8.82 | OPEN | OB_Bull BOS_Bull |
| 15 | 06-10 | 06-11 | 002335.SZ | - | 36.65 | - | - | 35.58 | 38.30 | OPEN | OB_Bull CHOCH_Bull |
| 16 | 06-11 | 06-12 | 002350.SZ | - | 14.31 | - | - | 12.87 | 16.63 | OPEN | OB_Bull CHOCH_Bull |
| 17 | 06-10 | 06-11 | 002415.SZ | - | 30.21 | - | - | 29.39 | 31.50 | OPEN | OB_Bull CHOCH_Bull |
| 18 | 06-10 | 06-11 | 002512.SZ | - | 4.09 | - | - | 3.94 | 4.33 | OPEN | FVG_Bull BOS_Bull |
| 19 | 06-10 | 06-11 | 002515.SZ | - | 7.39 | - | - | 7.13 | 7.81 | OPEN | FVG_Bull CHOCH_Bull |
| 20 | 06-10 | 06-11 | 002606.SZ | - | 13.58 | - | - | 13.06 | 14.44 | OPEN | FVG_Bull CHOCH_Bull |
| 21 | 06-10 | 06-11 | 002637.SZ | - | 11.46 | - | - | 10.99 | 12.16 | OPEN | OB_Bull CHOCH_Bull |
| 22 | 06-10 | 06-11 | 002678.SZ | - | 5.59 | - | - | 5.42 | 5.86 | OPEN | FVG_Bull CHOCH_Bull |
| 23 | 06-11 | 06-12 | 002789.SZ | - | 13.12 | - | - | 12.07 | 14.73 | OPEN | FVG_Bull BOS_Bull |
| 24 | 06-10 | 06-11 | 002824.SZ | - | 27.28 | - | - | 26.30 | 28.81 | OPEN | FVG_Bull CHOCH_Bull |
| 25 | 06-10 | 06-11 | 002833.SZ | - | 17.55 | - | - | 17.03 | 18.39 | OPEN | OB_Bull BOS_Bull |
| 26 | 06-12 | 06-15 | 002876.SZ | - | 30.01 | - | - | 27.84 | 33.61 | OPEN | FVG_Bull BOS_Bull |
| 27 | 06-10 | 06-11 | 002919.SZ | - | 20.20 | - | - | 19.64 | 21.04 | OPEN | FVG_Bull BOS_Bull |
| 28 | 06-10 | 06-11 | 002929.SZ | - | 59.89 | - | - | 57.96 | 62.82 | OPEN | OB_Bull BOS_Bull |
| 29 | 06-10 | 06-11 | 002943.SZ | - | 51.33 | - | - | 49.43 | 54.54 | OPEN | FVG_Bull BOS_Bull |
| 30 | 06-10 | 06-11 | 002948.SZ | - | 5.93 | - | - | 5.69 | 6.29 | OPEN | FVG_Bull CHOCH_Bull |
| 31 | 06-10 | 06-11 | 002952.SZ | - | 22.91 | - | - | 22.18 | 24.08 | OPEN | OB_Bull CHOCH_Bull |
| 32 | 06-10 | 06-11 | 300001.SZ | - | 36.80 | - | - | 35.67 | 38.71 | OPEN | OB_Bull BOS_Bull |
| 33 | 06-10 | 06-11 | 300012.SZ | - | 13.89 | - | - | 13.97 | 14.32 | OPEN | OB_Bull CHOCH_Bull |
| 34 | 06-11 | 06-12 | 300088.SZ | - | 8.00 | - | - | 7.03 | 9.46 | OPEN | FVG_Bull BOS_Bull |
| 35 | 06-10 | 06-11 | 300351.SZ | - | 16.11 | - | - | 15.68 | 16.78 | OPEN | OB_Bull CHOCH_Bull |
| 36 | 06-10 | 06-11 | 300395.SZ | - | 120.36 | - | - | 117.06 | 126.08 | OPEN | FVG_Bull BOS_Bull |
| 37 | 06-11 | 06-12 | 300410.SZ | - | 11.06 | - | - | 9.86 | 12.87 | OPEN | FVG_Bull BOS_Bull |
| 38 | 06-10 | 06-11 | 300469.SZ | - | 52.00 | - | - | 49.71 | 55.61 | OPEN | FVG_Bull CHOCH_Bull |
| 39 | 06-11 | 06-12 | 300472.SZ | - | 7.90 | - | - | 7.47 | 8.58 | OPEN | FVG_Bull CHOCH_Bull |
| 40 | 06-10 | 06-11 | 300473.SZ | - | 31.85 | - | - | 30.78 | 33.50 | OPEN | OB_Bull CHOCH_Bull |
| 41 | 06-12 | 06-15 | 300475.SZ | - | 193.00 | - | - | 173.93 | 221.62 | OPEN | FVG_Bull CHOCH_Bull |
| 42 | 06-11 | 06-12 | 300476.SZ | - | 340.06 | - | - | 300.48 | 399.68 | OPEN | FVG_Bull CHOCH_Bull |
| 43 | 06-10 | 06-11 | 300499.SZ | - | 34.71 | - | - | 33.11 | 37.12 | OPEN | OB_Bull CHOCH_Bull |
| 44 | 06-11 | 06-12 | 300593.SZ | - | 35.56 | - | - | 31.56 | 42.82 | OPEN | FVG_Bull CHOCH_Bull |
| 45 | 06-10 | 06-11 | 300782.SZ | - | 93.56 | - | - | 90.13 | 99.98 | OPEN | FVG_Bull BOS_Bull |
| 46 | 06-10 | 06-11 | 300823.SZ | - | 15.88 | - | - | 15.44 | 16.56 | OPEN | FVG_Bull CHOCH_Bull |
| 47 | 06-10 | 06-11 | 300849.SZ | - | 22.53 | - | - | 21.75 | 23.74 | OPEN | FVG_Bull BOS_Bull |
| 48 | 06-10 | 06-11 | 300860.SZ | - | 25.77 | - | - | 25.03 | 26.90 | OPEN | OB_Bull CHOCH_Bull |
| 49 | 06-10 | 06-11 | 300921.SZ | - | 17.60 | - | - | 16.95 | 18.62 | OPEN | OB_Bull CHOCH_Bull |
| 50 | 06-11 | 06-12 | 301002.SZ | - | 44.18 | - | - | 39.32 | 51.87 | OPEN | FVG_Bull BOS_Bull |
| 51 | 06-12 | 06-15 | 301002.SZ | - | 42.15 | - | - | 38.56 | 47.58 | OPEN | FVG_Bull BOS_Bull |
| 52 | 06-12 | 06-15 | 301029.SZ | - | 29.17 | - | - | 27.51 | 31.76 | OPEN | FVG_Bull CHOCH_Bull |
| 53 | 06-10 | 06-11 | 301046.SZ | - | 25.79 | - | - | 24.55 | 27.68 | OPEN | FVG_Bull CHOCH_Bull |
| 54 | 06-10 | 06-11 | 301070.SZ | - | 97.74 | - | - | 93.83 | 103.83 | OPEN | OB_Bull CHOCH_Bull |
| 55 | 06-11 | 06-12 | 301133.SZ | - | 40.45 | - | - | 36.69 | 46.45 | OPEN | FVG_Bull BOS_Bull |
| 56 | 06-12 | 06-15 | 301133.SZ | - | 40.18 | - | - | 35.35 | 47.45 | OPEN | FVG_Bull BOS_Bull |
| 57 | 06-10 | 06-11 | 301141.SZ | - | 47.98 | - | - | 46.72 | 50.24 | OPEN | OB_Bull CHOCH_Bull |
| 58 | 06-10 | 06-11 | 301171.SZ | - | 37.25 | - | - | 36.27 | 39.22 | OPEN | FVG_Bull BOS_Bull |
| 59 | 06-10 | 06-11 | 301191.SZ | - | 94.06 | - | - | 91.14 | 99.21 | OPEN | FVG_Bull BOS_Bull |
| 60 | 06-10 | 06-11 | 301232.SZ | - | 115.67 | - | - | 112.32 | 120.83 | OPEN | FVG_Bull CHOCH_Bull |
| 61 | 06-10 | 06-11 | 301260.SZ | - | 15.24 | - | - | 14.59 | 16.22 | OPEN | OB_Bull BOS_Bull |
| 62 | 06-12 | 06-15 | 301317.SZ | - | 57.00 | - | - | 51.66 | 65.34 | OPEN | FVG_Bull BOS_Bull |
| 63 | 06-10 | 06-11 | 301421.SZ | - | 87.61 | - | - | 84.88 | 91.74 | OPEN | FVG_Bull BOS_Bull |
| 64 | 06-10 | 06-11 | 301479.SZ | - | 61.92 | - | - | 60.10 | 64.78 | OPEN | FVG_Bull CHOCH_Bull |
| 65 | 06-10 | 06-11 | 301548.SZ | - | 71.11 | - | - | 68.97 | 74.67 | OPEN | OB_Bull CHOCH_Bull |
| 66 | 06-10 | 06-11 | 600020.SH | - | 3.99 | - | - | 3.86 | 4.19 | OPEN | OB_Bull CHOCH_Bull |
| 67 | 06-10 | 06-11 | 600207.SH | - | 6.50 | - | - | 6.26 | 6.92 | OPEN | FVG_Bull BOS_Bull |
| 68 | 06-10 | 06-11 | 600259.SH | - | 88.90 | - | - | 85.37 | 94.24 | OPEN | FVG_Bull CHOCH_Bull |
| 69 | 06-10 | 06-11 | 600336.SH | - | 7.05 | - | - | 6.85 | 7.38 | OPEN | FVG_Bull CHOCH_Bull |
| 70 | 06-10 | 06-11 | 600502.SH | - | 4.74 | - | - | 4.58 | 4.99 | OPEN | OB_Bull BOS_Bull |
| 71 | 06-10 | 06-11 | 600525.SH | - | 4.95 | - | - | 4.78 | 5.22 | OPEN | OB_Bull CHOCH_Bull |
| 72 | 06-10 | 06-11 | 600527.SH | - | 2.30 | - | - | 2.23 | 2.41 | OPEN | OB_Bull CHOCH_Bull |
| 73 | 06-10 | 06-11 | 600568.SH | - | 2.59 | - | - | 2.48 | 2.76 | OPEN | OB_Bull CHOCH_Bull |
| 74 | 06-10 | 06-11 | 600575.SH | - | 3.63 | - | - | 3.49 | 3.84 | OPEN | OB_Bull BOS_Bull |
| 75 | 06-11 | 06-12 | 600575.SH | - | 3.77 | - | - | 3.42 | 4.30 | OPEN | OB_Bull CHOCH_Bull |
| 76 | 06-10 | 06-11 | 600850.SH | - | 18.69 | - | - | 18.15 | 19.52 | OPEN | OB_Bull CHOCH_Bull |
| 77 | 06-10 | 06-11 | 600857.SH | - | 14.00 | - | - | 13.46 | 14.84 | OPEN | OB_Bull BOS_Bull |
| 78 | 06-10 | 06-11 | 601077.SH | - | 7.04 | - | - | 6.84 | 7.35 | OPEN | OB_Bull BOS_Bull |
| 79 | 06-09 | 06-10 | 601088.SH | - | 48.75 | - | - | 46.98 | 51.42 | OPEN | OB_Bull BOS_Bull |
| 80 | 06-11 | 06-12 | 601088.SH | - | 46.99 | - | - | 45.80 | 49.02 | OPEN | FVG_Bull BOS_Bull |
| 81 | 06-10 | 06-11 | 601233.SH | - | 21.57 | - | - | 20.58 | 23.37 | OPEN | FVG_Bull CHOCH_Bull |
| 82 | 06-09 | 06-10 | 601398.SH | - | 7.57 | - | - | 7.18 | 8.04 | OPEN | FVG_Bull CHOCH_Bull |
| 83 | 06-10 | 06-11 | 601577.SH | - | 9.70 | - | - | 9.32 | 10.27 | OPEN | OB_Bull CHOCH_Bull |
| 84 | 06-11 | 06-12 | 601588.SH | - | 1.91 | - | - | 1.73 | 2.20 | OPEN | FVG_Bull CHOCH_Bull |
| 85 | 06-11 | 06-12 | 601677.SH | - | 16.80 | - | - | 15.47 | 18.92 | OPEN | FVG_Bull BOS_Bull |
| 86 | 06-10 | 06-11 | 601816.SH | - | 5.02 | - | - | 4.85 | 5.28 | OPEN | FVG_Bull CHOCH_Bull |
| 87 | 06-10 | 06-11 | 601919.SH | - | 14.49 | - | - | 13.99 | 15.26 | OPEN | FVG_Bull BOS_Bull |
| 88 | 06-11 | 06-12 | 603001.SH | - | 9.77 | - | - | 8.73 | 11.34 | OPEN | FVG_Bull BOS_Bull |
| 89 | 06-12 | 06-15 | 603001.SH | - | 9.63 | - | - | 8.68 | 11.11 | OPEN | FVG_Bull BOS_Bull |
| 90 | 06-10 | 06-11 | 603048.SH | - | 19.20 | - | - | 18.41 | 20.42 | OPEN | OB_Bull CHOCH_Bull |
| 91 | 06-09 | 06-10 | 603060.SH | - | 7.16 | - | - | 6.84 | 7.65 | OPEN | FVG_Bull BOS_Bull |
| 92 | 06-11 | 06-12 | 603070.SH | - | 14.38 | - | - | 12.39 | 17.36 | OPEN | FVG_Bull CHOCH_Bull |
| 93 | 06-10 | 06-11 | 603093.SH | - | 18.10 | - | - | 17.26 | 19.37 | OPEN | OB_Bull CHOCH_Bull |
| 94 | 06-10 | 06-11 | 603159.SH | - | 27.23 | - | - | 25.97 | 29.24 | OPEN | FVG_Bull BOS_Bull |
| 95 | 06-11 | 06-12 | 603159.SH | - | 26.50 | - | - | 24.94 | 29.10 | OPEN | FVG_Bull CHOCH_Bull |
| 96 | 06-10 | 06-11 | 603228.SH | - | 75.25 | - | - | 72.48 | 79.85 | OPEN | FVG_Bull BOS_Bull |
| 97 | 06-10 | 06-11 | 603255.SH | - | 30.08 | - | - | 29.11 | 31.58 | OPEN | FVG_Bull CHOCH_Bull |
| 98 | 06-10 | 06-11 | 603368.SH | - | 16.33 | - | - | 15.60 | 17.43 | OPEN | OB_Bull CHOCH_Bull |
| 99 | 06-10 | 06-11 | 603383.SH | - | 28.87 | - | - | 27.85 | 30.78 | OPEN | OB_Bull CHOCH_Bull |
| 100 | 06-10 | 06-11 | 603586.SH | - | 18.06 | - | - | 17.55 | 18.83 | OPEN | OB_Bull BOS_Bull |
| 101 | 06-10 | 06-11 | 603637.SH | - | 18.00 | - | - | 17.21 | 19.58 | OPEN | FVG_Bull BOS_Bull |
| 102 | 06-11 | 06-12 | 603838.SH | - | 8.70 | - | - | 8.28 | 9.35 | OPEN | FVG_Bull BOS_Bull |
| 103 | 06-10 | 06-11 | 603906.SH | - | 23.34 | - | - | 22.63 | 24.65 | OPEN | OB_Bull BOS_Bull |
| 104 | 06-10 | 06-11 | 603937.SH | - | 13.36 | - | - | 12.96 | 14.01 | OPEN | OB_Bull BOS_Bull |
| 105 | 06-10 | 06-11 | 605016.SH | - | 24.40 | - | - | 23.77 | 25.43 | OPEN | OB_Bull CHOCH_Bull |
| 106 | 06-10 | 06-11 | 605218.SH | - | 16.87 | - | - | 16.22 | 17.94 | OPEN | OB_Bull CHOCH_Bull |
| 107 | 06-11 | 06-12 | 605336.SH | - | 16.23 | - | - | 15.23 | 17.75 | OPEN | FVG_Bull CHOCH_Bull |
| 108 | 06-10 | 06-11 | 688006.SH | - | 33.74 | - | - | 32.08 | 36.36 | OPEN | OB_Bull BOS_Bull |
| 109 | 06-10 | 06-11 | 688102.SH | - | 36.42 | - | - | 34.96 | 38.66 | OPEN | FVG_Bull CHOCH_Bull |
| 110 | 06-10 | 06-11 | 688109.SH | - | 79.24 | - | - | 76.67 | 83.11 | OPEN | OB_Bull CHOCH_Bull |
| 111 | 06-11 | 06-12 | 688135.SH | - | 35.57 | - | - | 29.80 | 44.42 | OPEN | FVG_Bull BOS_Bull |
| 112 | 06-12 | 06-15 | 688135.SH | - | 34.36 | - | - | 28.73 | 42.82 | OPEN | FVG_Bull BOS_Bull |
| 113 | 06-11 | 06-12 | 688187.SH | - | 55.95 | - | - | 48.17 | 67.73 | OPEN | FVG_Bull BOS_Bull |
| 114 | 06-10 | 06-11 | 688305.SH | - | 65.80 | - | - | 62.77 | 71.03 | OPEN | OB_Bull BOS_Bull |
| 115 | 06-10 | 06-11 | 688391.SH | - | 29.31 | - | - | 28.43 | 30.66 | OPEN | FVG_Bull CHOCH_Bull |
| 116 | 06-12 | 06-15 | 688392.SH | - | 153.67 | - | - | 136.21 | 179.85 | OPEN | FVG_Bull BOS_Bull |
| 117 | 06-10 | 06-11 | 688411.SH | - | 240.00 | - | - | 233.26 | 250.43 | OPEN | FVG_Bull BOS_Bull |
| 118 | 06-10 | 06-11 | 688419.SH | - | 45.93 | - | - | 44.03 | 48.84 | OPEN | FVG_Bull CHOCH_Bull |
| 119 | 06-10 | 06-11 | 688480.SH | - | 88.16 | - | - | 84.07 | 94.32 | OPEN | OB_Bull CHOCH_Bull |
| 120 | 06-11 | 06-12 | 688484.SH | - | 42.00 | - | - | 37.92 | 48.38 | OPEN | FVG_Bull CHOCH_Bull |
| 121 | 06-10 | 06-11 | 688515.SH | - | 190.00 | - | - | 181.26 | 206.55 | OPEN | OB_Bull BOS_Bull |
| 122 | 06-10 | 06-11 | 688521.SH | - | 228.11 | - | - | 221.36 | 239.07 | OPEN | FVG_Bull CHOCH_Bull |
| 123 | 06-10 | 06-11 | 688577.SH | - | 45.31 | - | - | 44.09 | 47.41 | OPEN | FVG_Bull BOS_Bull |
| 124 | 06-10 | 06-11 | 688593.SH | - | 30.35 | - | - | 29.04 | 32.32 | OPEN | FVG_Bull BOS_Bull |
| 125 | 06-11 | 06-12 | 688612.SH | - | 31.81 | - | - | 28.83 | 36.89 | OPEN | FVG_Bull CHOCH_Bull |
| 126 | 06-12 | 06-15 | 688612.SH | - | 31.15 | - | - | 28.59 | 35.14 | OPEN | FVG_Bull CHOCH_Bull |
| 127 | 06-10 | 06-11 | 688618.SH | - | 31.51 | - | - | 30.62 | 32.86 | OPEN | FVG_Bull BOS_Bull |
| 128 | 06-10 | 06-11 | 688629.SH | - | 138.60 | - | - | 134.82 | 144.63 | OPEN | FVG_Bull BOS_Bull |
| 129 | 06-10 | 06-11 | 688633.SH | - | 28.75 | - | - | 27.70 | 30.63 | OPEN | OB_Bull BOS_Bull |
| 130 | 06-11 | 06-12 | 688679.SH | - | 54.00 | - | - | 47.58 | 64.66 | OPEN | FVG_Bull BOS_Bull |

## NEXT_DAY_PENDING
None

## Latest production active picks
None: no /api/picks rows matched production active scope.
pick_scope_counts={"WATCH_ONLY": 49}
state_counts={"WATCH_ONLY": 49}

## Failures
- Data collection script timed out after 120s: /root/.hermes/scripts/v25/smc_morning_push.py
- Manual run timed out after 600s; do not rerun unchanged until smc_daily_ops child is cleared or preflight is decoupled.
- Kline refresh partial failure: 2883/4905 symbols failed; sample errors in ops_latest are JSON parse errors from empty upstream responses.
- Final delivery is this cron response; no send_message was called because cron instruction says system delivers final response.