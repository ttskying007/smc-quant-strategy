# 每日最新行情日期同步口径

## 适用场景

用户指出：每天执行后，回测、选股、实时、分析、复盘看起来都不是当前最新日期的数据。处理这类 SMC 前端/日常任务同步问题时，必须先统一日期口径，再判断是否真的没有候选。

## 核心原则

不要把“系统日期”“最新行情日”“选股入场日期”“历史交易日期”混在一起。

| 概念 | 含义 | 正确来源 |
|---|---|---|
| 系统日期 | 服务器当天日期，例如盘前 `20260603` | `date` / ops log `date` |
| 最新行情日 | 已下载 K 线数据中的最大交易日，例如 `20260602` | `kline_refresh.latest_counts` 最大 key |
| 最新有效选股日 | 通过生产门禁的候选 pick 日期 | `pick_date/select_date/entry_date` 最大值 |
| 回测/分析/复盘窗口结束日 | 页面默认统计窗口结束日期 | 应默认使用“最新行情日”，不是旧 metrics.window_end |

## 必做修复/检查

1. 新增统一函数，例如 `_latest_data_date(ops=None)`：
   - 优先读 `ops_latest.json.kline_refresh.latest_counts` 或 `kline_refresh.summary.latest_counts` 的最大日期；
   - 再 fallback 到 `daily_scan_merge.latest_scan_date`；
   - 不要把 `ops.date` 当作最新行情日，因为盘前/休市时系统日期会晚于最后一个交易日。
2. 回测 `/backtest`：默认 `end` 应使用 `_latest_data_date()`，页面明确显示“最新行情日”。
3. 选股 `/monitor`：页面显示 `数据日期:<latest_data_date>`，同时保留“最新有效选股日”。两者不同不代表页面没同步。
4. 选股 API `/api/picks`：给每条 pick 增加 `data_date`，方便前端/测试直接验证页面日期口径。
5. 实时 `/live` 与 `/api/live-prices`：返回/展示 `dataDate:<latest_data_date>`；休市也要显示，不能只显示“休市中”。
6. 分析 `/analysis`、复盘 `/autopsy`：默认窗口结束日使用 `_latest_data_date()`，不是旧 `metrics.window_end`。
7. 日志 `/logs`：新增“页面日期同步状态”表，直接列出回测/选股/分析/复盘各自同步到的日期。

## 重要 pitfall

如果最新行情日没有生产候选，日志不要写成容易误解的：

```text
最新行情日选股=0；最新行情日=20260602；系统日=20260603；...
```

应写成明确区分页面同步和候选结果的结论：

```text
页面同步检查：回测/选股/分析/复盘已按最新行情日=20260602展示；生产有效选股=0。
V66当前候选最新日期=...；V65源最新日期=...；V66保留交易最新日期=...。
结论：日期已同步，问题是最新行情日没有通过V66生产门禁的入场候选。
```

这样用户能一眼看出：页面是否同步到最新行情日，和最新行情日是否产生候选，是两个不同问题。

## 验证脚本模式

验证时不要只看一个页面。至少检查：

```text
/backtest   包含最新行情日，不包含旧 window_end
/monitor    包含 数据日期:<latest_data_date>
/api/picks  每条 pick 有 data_date=<latest_data_date>
/live       标题/接口包含 dataDate=<latest_data_date>
/analysis   当前窗口 start~<latest_data_date>
/autopsy    当前窗口 start~<latest_data_date>
/logs       有“页面日期同步状态”，且 stale_reason 不再误导
```

若 `/logs` 仍出现旧的 `20260521`，先判断来源：可能只是 `V65源最新日期` 或历史 rejected sample，不一定是页面窗口未同步。页面同步判断以“页面日期同步状态”和各页面默认窗口为准。