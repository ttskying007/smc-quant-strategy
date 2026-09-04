# SMC 次日模拟买入状态机修复记录

适用场景：选股页/每日选股已有候选，但实时页没有进入监控；或用户指出“昨天选股，今天已经交易时段，为什么还没买入/持仓”。

## 正确机制

A股日线选股必须区分三类日期/状态：

| 字段/状态 | 含义 |
|---|---|
| `select_date` / `pick_date` | 信号/选股日期 |
| `join_date` / `joined_at` | 加入候选池时间 |
| `buy_date` / `created_at` | 实际模拟买入时间 |
| `NEXT_DAY_PENDING` | 已入候选池，等待下一交易日模拟买入；不算持仓 |
| `OPEN` | 已在下一交易日模拟买入；才算实时持仓 |

硬规则：

```text
select_date < buy_date
```

同日选股不得同日写 `BUY`，不得同日进入 `OPEN`。

## 状态流

```text
当日/盘后/非交易日选股
→ NEXT_DAY_PENDING
→ 下一交易日 09:30-15:00 拿实时价模拟买入
→ OPEN
→ 写 trade_ledger BUY
→ 进入 /api/live-prices 实时监控
```

## 关键坑

1. 只阻断同日 BUY 不够。
   - 如果没有 `NEXT_DAY_PENDING → OPEN` 的自动填单逻辑，候选会永远卡在 pending，用户会看到“选股页有，下方/实时监控没有”。

2. 每日选股文件里的 `positions=[]` 不代表没有选股。
   - `active_count/categories` 代表今日候选。
   - `positions` 常只代表本次新增到监控状态的记录。

3. 实时页只应该显示 `OPEN`。
   - pending 候选可在选股页或独立“待次日买入”区显示，但不能算实时持仓。

4. 次日买入后必须重算执行字段。
   - `entry_price` 使用次日实时价/开盘价。
   - `execution_price_source` 标明来源，如 `tencent_last`。
   - `joined_at` 保留原候选加入时间。
   - `created_at` 更新为实际模拟买入时间。
   - `trade_ledger` 写 `BUY`，`select_date` 保留昨日，`buy_date` 为今日。

## 推荐实现点

在 `smc_monitor_state.py` 中保持两个独立动作：

```text
ingest_daily_picks():
  当日 auto_daily active pick → NEXT_DAY_PENDING，不写 BUY

fill_pending_orders():
  若当前是下一交易日交易时段，pending → OPEN，并写 BUY
```

并在实时刷新入口调用：

```text
update_with_live_results():
  先 fill_pending_orders()
  再进行 SL/TP 实时检查
```

交易时段判断建议至少包含：

```text
weekday < 5
09:30 <= now < 15:00
pick_date < today
```

## 验证清单

修复后必须同时验证：

| 检查 | 要求 |
|---|---|
| positions | 昨日 pending 已转 `OPEN` |
| ledger | 生成 `BUY`，且 `select_date < buy_date` |
| 同日违规 | `same_day_buy_violations == 0` |
| 实时页 | `/api/live-prices` 包含新转入股票 |
| pending 幂等 | 第二次刷新不重复写 BUY |
| 页面 | `/live`、`/monitor`、`/logs` 正常 |

示例验证字段：

```json
{
  "select_date": "20260603",
  "buy_date": "20260604",
  "status": "OPEN",
  "filled_from_status": "NEXT_DAY_PENDING",
  "execution_price_source": "tencent_last"
}
```
