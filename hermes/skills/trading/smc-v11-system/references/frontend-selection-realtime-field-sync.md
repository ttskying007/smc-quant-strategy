# SMC 前端选股/实时页字段同步检查清单

适用场景：用户要求修复选股页、实时页、K线页出现空列/空值/字段不同步，尤其是 watchlist/active picks 与历史 trades 字段不一致时。

## 必须优先确认的源文件与接口

- 选股页候选源必须是当前 watchlist/active candidates，不得用历史 trades 伪装。
- V46+ 常见候选源：`v46_1_watchlist.json` 或当前生产版本对应 watchlist/picks 契约文件。
- 前端 API 需同时验证：
  - 选股页候选接口
  - 实时页接口
  - K线详情接口
  - `/api/v45/report?ver=...` 等历史兼容接口（如页面仍依赖）

## 选股页新增/修复字段

当用户要求“增加一列选股日期、加入日期”时，不要只改表头。必须端到端补齐：

1. 后端 row 构造：输出 flat 字段。
2. 前端 table columns：增加显示列。
3. JS 渲染映射：确认字段名一致。
4. API curl 验证：抽取首批 rows 检查字段非空。
5. 浏览器验证：页面可见列存在且值显示。

推荐字段映射顺序：

```text
选股日期: pick_date -> conf_date -> retrace_date -> signal_date -> entry_date
加入日期: join_date -> added_date -> watch_date -> pick_date -> conf_date -> signal_date
```

注意：watchlist rows 可能没有 `entry_date`，不能只用 entry_date 做近期过滤或显示。

## zone 为空修复

“下面的引擎 zone 为空”通常是 raw/display 字段或旧新契约命名不一致导致。不要只在 JS 里显示 `-`，要保留可审计的 fallback：

```text
zone: zone -> zone_type -> signal_type -> entry_type -> setup_type -> signal_name
```

如果 zone 是嵌套 dict，显示应取：

```text
zone.type -> zone.kind -> zone.name
```

并保留 raw zone 对象供 K线/复盘使用，避免 display 字符串覆盖结构化数据。

## 实时页成本线为空修复

实时页“成本线为空”常见于版本字段差异：

```text
cost_line: smart_money_cost -> cost -> entry_price -> signal_price -> price
```

修复时必须同步：

- API 返回字段
- 前端实时卡片
- K线 horizontal line 绘制
- 选股/持仓推送里的成本字段

验证时至少检查一只有持仓/候选的股票，确认 API JSON 与图上成本线一致。

## 实时页波动为空修复

“波动为空”需先确认是实时源字段缺失还是前端字段名错误。推荐 fallback：

```text
volatility: volatility -> vol_pct -> amplitude_pct -> intraday_range_pct -> range_pct -> risk_pct
```

如果实时源无波动字段，可由价格计算：

```text
(high - low) / prev_close * 100
```

或无 prev_close 时：

```text
(high - low) / current_price * 100
```

不要把无法计算的波动静默显示为空；显示 `--` 前必须在 API 中明确 `volatility_source` / `volatility_missing_reason`。

## 选股候选与实时监控状态机

当选股页/每日选股已有候选，但实时页没有显示时，先区分：

```text
ACTIVE_CANDIDATE / NEXT_DAY_PENDING = 候选，不算持仓
OPEN = 已模拟买入，才进入实时监控
```

A股日线系统中，当日/盘后/非交易日选股不得直接写 `BUY` 或 `OPEN`，应先进入 `NEXT_DAY_PENDING`；但下一交易日交易时段内必须自动执行 pending fill：

```text
NEXT_DAY_PENDING → OPEN + trade_ledger BUY
select_date/pick_date 保留选股日，buy_date/created_at 使用实际模拟买入日
```

若用户指出“昨天选股，今天已交易时段还没进入实时监控”，这不是前端字段问题，而是状态机缺少或未触发 `fill_pending_orders()`。详见 `references/next-day-pending-fill-state-machine.md`。

## 验收标准

修复完成后必须同时验证：

| 检查 | 要求 |
|---|---|
| API | 新字段存在且非空率合理 |
| 选股页 | 有“选股日期”“加入日期”两列 |
| 引擎/详情区 | zone 不为空，能追溯原始字段 |
| 实时页 | 成本线、波动不为空或有明确缺失原因 |
| K线图 | 成本线与 API 字段一致 |
| 当前候选源 | 使用最新 watchlist/active candidates，不用历史 trades 伪装 |

## 常见错误

- 只改 HTML 表头，未补后端字段。
- 用 `entry_date` 作为 watchlist 日期，导致当前候选全部空。
- 历史 trades 有 zone，但当前 watchlist 没 zone，前端未做 fallback。
- 实时页成本字段仍读旧 `cost`，但新版本输出 `smart_money_cost`。
- 波动字段为空时直接显示空字符串，没有计算 fallback，也没有 missing reason。
