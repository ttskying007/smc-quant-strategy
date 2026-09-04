# SMC monitor 状态机：当日选股不得直接写 BUY

## 触发场景

用户发现生产监控链路中，当日 `ACTIVE_CANDIDATE` 被 `ingest_daily_picks()` 直接写入 `positions.json` 的 `OPEN`，同时写入 `trade_ledger.json` 的 `BUY`。这会把“当日选股候选”伪装成“已买入持仓”，违反 A 股 T+1 和生产选股语义。

## 正确状态机

```text
全市场最新K线扫描产生 ACTIVE_CANDIDATE
→ ingest_daily_picks(source='auto_daily')
→ 若 pick_date/select_date/entry_date == 当前日期：
   status = NEXT_DAY_PENDING
   execution_price_source = candidate_price_no_execution
   不写 trade_ledger BUY
   不进入实时持仓 OPEN
→ 仅次日开盘且通过执行门禁后，才允许 BUY/OPEN
```

## 代码级修复模式

目标文件通常是：

```text
/root/.hermes/scripts/smc_monitor_state.py
```

关键点：

1. 在 `ingest_daily_picks()` 前置判断 `is_same_day_pick(p)`。
2. 对同日 `auto_daily` 候选：
   - `status='NEXT_DAY_PENDING'`
   - `pending_reason='SAME_DAY_PICK_WAIT_NEXT_TRADING_DAY'`
   - 不 append `make_buy_ledger()`
3. 在 `to_position()` 中，同日候选不要用 Tencent 实时价覆盖成成交价；保留候选价并标记：
   - `execution_price_source='candidate_price_no_execution'`
4. `existing_live_keys` 不应只看 `OPEN`，也要避免同一候选重复生成 pending。

## 数据清理流程

当已有错误 BUY/OPEN 时，必须同时清理三处，不能只改 positions：

| 文件 | 动作 |
|---|---|
| `positions.json` | 目标股票改为 `NEXT_DAY_PENDING`，删除 `closed_at/close_reason/exit_price/review_id` |
| `trade_ledger.json` | 删除目标 `position_id` 的 BUY/SELL 残留 |
| `closed_reviews.json` | 删除目标 `position_id` 的 review 残留 |

清理前必须备份：

```text
/root/.hermes/smc_monitor/backups/<reason>_<timestamp>/
```

## 验证门禁

修复后必须验证：

```text
same_day_or_after15_buy_violations == 0
target_ledger_remaining == 0
target_reviews_remaining == 0
target_open == 0
target_pending == 目标数量
/api/live-prices 不包含回退股票
selftest ok == true
```

同时运行：

```bash
python3 -m py_compile /root/.hermes/scripts/smc_monitor_state.py
python3 /root/.hermes/scripts/v25/smc_closed_loop_ops.py selftest
```

## 易错点

- 不要只删除 BUY；若次日监控已经对错误 OPEN 产生 SELL/review，也必须一并删掉。
- 不要把 `ACTIVE_CANDIDATE` 的候选价叫做成交价；字段必须能区分 `candidate_price_no_execution`。
- 不要把历史交易文件当成当前选股源；实时持仓只应来自真正 `OPEN`。
- 用户会检查前端实时页；修复必须重启/验证 8890 API 与页面，而不是只改 JSON。
