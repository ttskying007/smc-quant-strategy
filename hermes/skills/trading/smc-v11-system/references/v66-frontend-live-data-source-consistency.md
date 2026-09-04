# V66 前端/实时/选股数据源一致性审计

## 触发场景

用户反馈：

- 前端显示内容与报告/接口输出不一致
- 选股页显示的数量、实时页数量、positions 数量对不上
- 胜率看起来很高，但实时 SL 很高或当前选股质量很差
- 选股页字段已经不空，但用户仍认为“显示不符合”

这类问题不能只查字段是否为空；必须先分清**前端正在展示哪一个数据源**。

## 必查数据源

| 表面 | 典型入口 | 语义 |
|---|---|---|
| 当前选股 API | `/api/picks` | 当前候选/观察列表，来自 active pick file |
| 选股页当前有效表 | `/monitor` 第一张候选表 | 当前 active candidates |
| 选股页监控表 | `/monitor` “每日选股→实时监控” | `positions.json` 的 OPEN/NEXT_DAY_PENDING/WATCH_ONLY 历史汇入仓位 |
| 实时页 | `/live` / `/api/live-prices` | OPEN + NEXT_DAY_PENDING 实时监控仓位 |
| 历史回测 | `v66_trades.json` | 历史已闭合交易，不等于当前选股 |
| 实时闭环 | `trade_ledger.json` / review samples | BUY/SELL 和 SL/TP 复盘闭环 |

## 审计步骤

1. **接口字段合同先验收，但不要停止在这里**
   - `/api/picks`: `pick_date/select_date`, `join_date`, `zone_type/zone_low/zone_high`, `cost_line/smart_money_cost`, `volatility_pct/risk_pct/v25_vol_class` 空值统计。
   - `/api/live-prices`: `pickDate`, `joinDate`, `zoneType/zoneLow/zoneHigh`, `costLine`, `volClass` 空值统计。
   - 空值为 0 只说明字段合同修复，不说明数据源一致。

2. **分开统计 current picks、positions、ledger**
   - `v66_picks.json` / `v26_picks.json`: `pick_scope`, `is_active_pick`, `pick_date`, `zone_type`, `risk_pct`, `retrace_depth_pct`。
   - `positions.json`: `status` 分布（OPEN/NEXT_DAY_PENDING/WATCH_ONLY/CLOSED）、`entry_zone_relation`、`risk_pct`、`zone_type`。
   - `trade_ledger.json`: BUY vs SELL 数量、`zone_type`/`zone`/`cost_line`/`volatility_pct` 空值。

3. **显式区分三种“当前”**
   - 今日 active candidates：只能由 `pick_scope == ACTIVE_CANDIDATE and is_active_pick == True` 定义。
   - 实时持仓：只能由 `positions.status in (OPEN, NEXT_DAY_PENDING)` 定义。
   - 观察/拒绝：WATCH_ONLY/REJECTED 不应混进“当前有效选股”口径。

4. **数量不一致时优先查代码入口**
   - `get_active_picks()` 是否把 `WATCH_ONLY` 也返回给 `/api/picks`。
   - `build_monitor()` 是否把 `positions.json` 的历史监控表放在选股页上方/下方，导致用户以为是当前选股。
   - `_api_live_prices()` 是否只取 OPEN/NEXT_DAY_PENDING，还是混入 active pick file。

5. **胜率/SL 口径一致性**
   - 历史 `v66_trades.json` 的 WR 不能代表当前扫描候选。
   - 如果 current scan 使用 `daily_scan.py`，而历史回测来自另一套 engine/信号源，必须声明“不可直接比较”。
   - 必须重跑全市场质量分桶：`zone_type`, `in_zone`, `sl_pct`, `retrace`, `sweep`, `state`。

## 高风险症状

| 症状 | 解释 |
|---|---|
| `/api/picks` 字段不空，但页面仍“不符合” | 多半是 current picks 与 positions 历史仓位混在同页展示 |
| `/monitor` 显示有效选股很少，但实时页很多 | 实时页来自历史 OPEN/PENDING，不是今日有效选股 |
| V66 历史 WR 很高，但当前 SL 多 | 历史 trades 与当前 Phase2 scan 不是同源口径 |
| BUY 很多、SELL=0 | 实时闭环断裂，SL/TP 没有进入复盘学习 |
| active 中 `entry <= SL` 或 `entry < zone_low` | 硬机制错误，必须先隔离再谈参数 |

## 修复/报告要求

报告必须用表格列出：

1. `/api/picks`、`/api/live-prices` 字段空值计数。
2. current picks vs positions vs ledger 的数量和来源。
3. active candidates 的硬错误：`entry<=SL`, `entry<zone_low`, `risk<2.5`, `risk>阈值`, `retrace>70/90`。
4. 历史回测 WR 与当前全市场 Phase2 WR 的口径差异。
5. 明确指出哪些页面显示的是“当前选股”，哪些是“历史汇入仓位”。

不要把“字段已经有值”当作完成。Lei 会按前端真实语义和数量交叉核对。