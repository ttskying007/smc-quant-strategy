# V12 完整交易日志格式

## 日志字段 (15列)

每笔交易包含以下完整信息，便于人工排查和审计：

| 列 | 字段 | 说明 |
|----|------|------|
| 1 | symbol | 股票代码 |
| 2 | entry_date | 实际买入日期 (YYYYMMDD) |
| 3 | signal_date | 信号触发日期 |
| 4 | signal_type | 信号类型 (OB_Bull为主) |
| 5 | signal_price | 信号触发价格 |
| 6 | signal_idx | 信号所在bar索引 |
| 7 | entry_idx | 入场bar索引 |
| 8 | entry_price | 实际入场价格 |
| 9 | entry_type | 入场方式: retrace/immediate/breakout |
| 10 | retrace_pct | 回撤百分比 (入场价相对成本线) |
| 11 | cost_line | 聪明钱成本线 (OB下沿/摆动低点) |
| 12 | combo | 信号组合: standalone 或 OB@X→LIQ@Y→CHOCH@Z |
| 13 | has_sweep | 是否有流动性清扫 |
| 14 | has_choch | 是否有CHOCH确认 |
| 15 | weekly_bull | 周线是否bullish |
| 16 | market_state | 市场状态: trending_up/ranging/volatile/trending_down |
| 17 | atr_pct | ATR波动率% |
| 18 | sl_price | 止损价格 |
| 19 | sl_pct | 止损百分比 |
| 20 | tp_pct | 目标止盈百分比 |
| 21 | exit_date | 实际卖出日期 |
| 22 | exit_price | 实际卖出价格 |
| 23 | exit_reason | 出场原因: SL_hit / time_stop / timeout |
| 24 | exit_detail | 出场详情: TP1/TP2/SL价格组合 |
| 25 | pnl_pct | 盈亏百分比 |
| 26 | won | 是否盈利 |
| 27 | rr | 风险回报比 |
| 28 | hold_bars | 持仓bar数 |
| 29 | tp1_hit | TP1是否命中 |
| 30 | tp2_hit | TP2是否命中 |

## CSV输出

文件: `/root/.hermes/smc_opt_v12/v12_trade_log.csv`

Excel可直接打开，支持筛选/排序。JSON版: `v12_complete.json`。

## 前端显示

前端K线页面 (/kline) 交易记录表展示14列：
买入日 | 买入价 | 卖出日 | 卖出价 | 信号 | 信号价 | 入场 | 回撤% | 出场原因 | PnL | SL | RR | 持仓

悬停提示 (tooltip) 显示完整贸易上下文，包括信号日期、周线状态、市场状态等。
