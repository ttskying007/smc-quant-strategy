# V12 详细交易日志规范 (2026-05-15)

## 文件名
- JSON: `/root/.hermes/smc_opt_v12/v12_complete.json`
- CSV: `/root/.hermes/smc_opt_v12/v12_trade_log.csv` (Excel直接打开)

## 完整字段清单 (30字段)

| # | 字段 | 类型 | 说明 | 示例 |
|---|------|------|------|------|
| 1 | symbol | str | 股票代码 | 301137.SZ |
| 2 | entry_date | str | 买入日期 | 20250609 |
| 3 | signal_date | str | 信号发生日期 | 20250606 |
| 4 | signal_type | str | 信号类型 | OB_Bull |
| 5 | signal_price | float | 信号触发价格 | 31.79 |
| 6 | signal_idx | int | 信号bar索引 | 75 |
| 7 | entry_idx | int | 买入bar索引 | 76 |
| 8 | entry_price | float | 买入成交价 | 32.39 |
| 9 | entry_type | str | 入场方式 | retrace |
| 10 | retrace_pct | float | 回撤到成本线的距离% | 1.89 |
| 11 | cost_line | float | 聪明钱成本线价格 | 31.79 |
| 12 | entry_detail | str | 入场详细描述 | retrace@32.39 retrace=1.9% |
| 13 | combo | str | 信号组合类型 | standalone / OB@266→LIQ@267→CHOCH@273 |
| 14 | has_sweep | bool | 是否有流动性清扫 | True |
| 15 | has_choch | bool | 是否有CHOCH确认 | True |
| 16 | weekly_bull | bool | 周线是否bullish | False |
| 17 | market_state | str | 市场状态 | trending_up/ranging/volatile/trending_down |
| 18 | atr_pct | float | ATR百分比 | 0.0154 |
| 19 | sl_price | float | 止损价格 | 14.205 |
| 20 | sl_pct | float | 止损百分比 | 34.96 |
| 21 | tp_pct | float | 止盈目标百分比 | 3.1 |
| 22 | exit_date | str | 卖出日期 | 20250610 |
| 23 | exit_bar | int | 卖出bar索引 | 77 |
| 24 | exit_price | float | 卖出价格 | 41.31 |
| 25 | exit_reason | str | 出场原因(大类) | SL_hit / time_stop / timeout |
| 26 | exit_detail | str | 出场详细描述 | TP1+SL=41.31+SL_hit |
| 27 | pnl_pct | float | 盈亏百分比 | 26.03 |
| 28 | won | bool | 是否盈利 | True |
| 29 | rr | float | 盈亏比 | 1.39 |
| 30 | hold_bars | int | 持仓bar数 | 1 |
| 31 | tp1_hit | bool | TP1是否命中 | True |
| 32 | tp2_hit | bool | TP2是否命中 | True |

## 信号组合格式
- 独立信号: `standalone`
- SMC序列: `OB@{bar}→LIQ@{bar}→CHOCH@{bar}` (按时间顺序排列)

## 出场原因分类
- `SL_hit`: 追踪止损被触发
- `time_stop`: 30bar超时止损
- `timeout`: 40bar超时退市

## 出场详情格式
- `TP1`: 50%仓位在TP1止盈
- `TP1+TP2`: 80%仓位在TP2止盈
- `SL=xx.xx+SL_hit`: 追踪止损触发，标注止损价
- `time_stop`: 30bar超时
- 组合: `TP1+SL=41.31+SL_hit` (部分TP后，剩余被SL)

## V12全量统计
- 15,029笔交易 / 4,702只股票
- WR=99.1% / 均盈=+9.80%
- TP1命中率=96.5%
- 信号组合(OB+LIQ+CHOCH序列): 1,119笔 (7.4%)
- 出场: SL_hit 88.9%, time_stop 11.0%, timeout 0.1%

## API接口
GET `/api/kline_full?symbol=301137.SZ&tf=daily&ver=V12`
返回包含: klines, signals_list, swings, trades (含全部32字段)
