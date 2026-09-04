# V66 监控字段完整性与生产门禁复核要点

适用场景：用户要求“再次全面检查前面发现的问题是否都解决”，或选股页/实时页出现日期、引擎、Zone、成本线、波动、操作记录字段为空，以及生产门禁样本仍混入可执行 OPEN。

## 必查范围

1. 服务与编译
   - `smc_unified.py` 必须在线监听 8890。
   - `smc_monitor_state.py`、`smc_unified.py`、`v25/smc_morning_push.py`、`v25/smc_daily_ops.py` 必须 `py_compile` 通过。

2. 选股 API 与选股页
   - `/api/picks` 当前有效候选必须来自最新扫描/watchlist，不可由历史 trades 伪装。
   - 每条候选必须有：`pick_date/select_date`、`join_date`、`engine`、`zone_type`、`zone_low/zone_high`。
   - `/monitor` 页面必须可见：`选股日期`、`加入日期`、`引擎`、`Zone`、`最后扫描`、`扫描行情日`、`WATCH_ONLY` 及拒绝原因。

3. 实时 API 与实时页
   - `/api/live-prices` 只应返回可执行 `OPEN`，不应混入 `WATCH_ONLY`。
   - 每条实时记录必须有：`entryDate`、`pickDate`、`joinDate`、`costLine`、`volClass`、`zoneLow/zoneHigh`、`entryZoneRelation`、`productionGate`。
   - `/live` 页面必须可见：成本线、波动、买入/卖出操作记录、操作记录的引擎列和 Zone 列。

4. 操作记录 ledger
   - `trade_ledger.json` 里的历史记录也要检查，不能只看前端兜底后的展示。
   - `engine` 缺失必须回填；新增记录的源头 `append_trade_event()` 应有兜底：`raw.engine -> pos.engine -> 'V66'`，防止未来再产生空引擎。
   - `zone` 缺失必须回填或由前端/API兜底展示，但复核时要同时查原始 ledger 和页面展示。

5. 生产门禁与历史隔离
   - `production_gate_current.action == WATCH_ONLY` 或带 `production_warning` 的样本，不得继续留在可执行 `OPEN`。
   - 不合格历史样本保留审计，但状态应转为 `WATCH_ONLY`，并写清 `reject_reason`、`legacy_status_before_gate`、`reconciled_at`。
   - 示例拒绝：过期选股 `STALE_PICK_*TRD`、入场价偏离 Zone `PRICE_ABOVE_ZONE_*%`。

6. T+1
   - ledger 中 `SELL` 的 `buy_date == sell_date` 必须为 0。
   - 当日买入不允许触发当日 SL/TP 卖出状态。

7. 扫描元信息
   - `/api/live-prices.scanMeta` 和 `/root/.hermes/smc_monitor/ops_latest.json` 必须一致。
   - 必须有：`data_date/latest_scan_date/last_scan_at/scan_returncode/kline_ok/kline_failed`。

## 复核脚本思路

- 同时请求：`/api/picks`、`/api/live-prices`、`/api/monitor/state`、`/monitor`、`/live`。
- 对每个字段做缺失计数，而不是只抽样看页面。
- 对 ledger 做原始 JSON 检查：`engine` 和 `zone` 缺失数必须为 0。
- 用浏览器实际打开 `/monitor` 和 `/live`，确认页面可见字段，不只依赖 API。

## 常见遗漏

- 前端/API 已经通过 fallback 显示正常，但原始 `trade_ledger.json` 仍有历史空 `engine`；这会在后续复核中再次暴露。修复应同时回填历史数据，并在 `append_trade_event()` 源头加默认兜底。
- 生产门禁上线后，已有 OPEN 里可能仍残留应该被隔离的历史样本；复核时要把 `production_gate_current.action == WATCH_ONLY` 的 OPEN 转为 WATCH_ONLY，而不是只标 warning。
- GitNexus `detect-changes` 在非 git 仓库会失败；这不是功能阻塞，复核时记录为环境限制即可，不要把它当成业务验收失败。

## 完成标准

表格化输出至少包含：服务、编译、选股日期、加入日期、引擎、Zone、实时成本线、波动、操作记录引擎/Zone、T+1、生产门禁、扫描元信息、浏览器页面可见性。所有缺失计数必须为 0；如果发现 1 项失败，先修复并重跑完整复核，再给结论。