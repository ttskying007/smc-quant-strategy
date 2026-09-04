# V66 T+1, K-line sync, and 2026 low-WR review lessons

Session learning from 2026-05-28 SMC maintenance.

## Hard release gate: A-share T+1

A-share backtests and execution must never contain same-day buy/sell exits.

Required implementation pattern:

1. Add a version-specific `vXX_t1_audit.py`.
2. Audit every trade using normalized date strings: `entry_date` vs `exit_date`.
3. If any `entry_date == exit_date`, release gate fails.
4. The engine must either skip same-day exit checks or shift the exit evaluation to the next eligible trading day.
5. `vXX_release_gate.py` must include a check named `t1_no_same_day_exit`.
6. Daily closed-loop scripts must run `vXX_t1_audit.py` before `vXX_release_gate.py`.

Verified V66 result:

```json
{
  "n_trades": 137,
  "violation_count": 0,
  "pass": true
}
```

## K-line/backtest sync pitfall

When a backtest row exists but the K-line chart has no marker or lower trade record, do not assume frontend rendering is broken. First check whether the trade dates exist in the loaded K-line cache window.

Observed cause:

- Some old trades were outside `daily_300` cache date coverage.
- The trade existed in the backtest list, but `entry_date`/`exit_date` were not present in the K-line bars currently loaded by `/api/kline_full`, so there was nothing to anchor on the chart.

Verification pattern:

1. For each trade, map `symbol` like `002235.SZ` to cache files like `002235_SZ_daily_300.json` or longer `daily_750.json`.
2. Normalize bar dates from `t` or `date` fields.
3. Check both `entry_date` and `exit_date` exist in loaded bars.
4. Then verify `/api/kline_full?symbol=...&tf=daily&ver=VXX` returns nonzero `trade_count` and `highlight` for an in-window trade.

If markers are missing only for out-of-window historical trades, fix by expanding the K-line window or falling back to longer cache, not by changing trade data.

## 2026 low-WR diagnosis pattern

Do not diagnose low WR from aggregate metrics. Slice the affected date window and review losses by:

- setup family (`v59_setup_family`)
- `zone_type`
- `conf_type`
- BQ score
- `near_high_pct`
- `range_atr`
- body/volume ratios
- exit reason
- whether the failure was signal accuracy, entry timing, or exit mechanics

In the 2026-01-01..2026-05-28 window, V65 had:

```text
18 trades, WR 77.78%, avg_pnl 10.246%
```

Loss diagnosis showed the main issue was not T+1 or missing chart markers. The weak subset was REENTRY:

- BQ < 60 weak reentry.
- `near_high_pct == 0` plus expanded `range_atr >= 4.4`, i.e. exact-high breakout after an already expanded 20-day range.

## V66 surgical overlay

V66 fixed the issue with a narrow pre-entry gate on top of V65:

```text
For REENTRY_SETUP:
  reject if breakout_quality_score < 60
  reject if near_high_pct == 0 and range_atr >= 4.4
```

This preserved most V65 trades while improving the troubled window:

```text
V65 full: 143 trades, WR 88.81%, avg_pnl 20.035%, avg_R 4.865
V66 full: 137 trades, WR 90.51%, avg_pnl 20.649%, avg_R 5.016

V65 2026 window: 18 trades, WR 77.78%, avg_pnl 10.246%
V66 2026 window: 14 trades, WR 92.86%, avg_pnl 13.162%
```

## Phone-readable report format

For SMC push/report output, prefer Markdown tables with short Chinese column names and clear row structure. Long prose lists are hard to read on mobile.

Recommended sections:

```markdown
## 持仓监控
| # | 买入日 | 代码 | 名称 | 成本 | 现价 | 盈亏 | 止损 | 止盈 | 状态 | 信号 |

## 今日选股
| # | 标识 | 日期 | 代码 | 名称 | 成本 | 止损 | 止盈 | 状态 | 信号 | BQ |
```
