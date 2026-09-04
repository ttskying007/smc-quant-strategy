# V88 实盘买入与回测可成交入场合同（2026-06-15）

## 触发场景
用户指出：选股后不能继续买入 5 月旧候选；实际股价已经与策略入场价/历史合同价有较大差距。若当日选股仍在交易时间，应按最新价格买入；非交易时间应等次日开盘/实时价或设定的有效入场区间，不能倒推历史价格，否则存在未来函数/不可成交问题。

## 持久规则
1. **实时执行价不能使用历史合同价**：`contract_source` / V88/V90/V91 的 `entry_price` 只能作为计划价/回测价，不能作为真实成交价。
2. **交易时间内选股**：如果 `market_entry_allowed()` 为真，`ingest_daily_picks()` / `to_position()` 必须调用 `live_execution_price()`，用腾讯实时价填入 `entry_price`，`execution_price_source=tencent_last|tencent_open`。
3. **非交易时间选股**：不得直接 `OPEN`；必须进入 `NEXT_DAY_PENDING`，`pending_reason=MARKET_CLOSED_WAIT_NEXT_OPEN`，下一个交易时段再按实时价重新过 `production_entry_gate()`。
4. **旧候选门禁**：超过 3 个交易日的 pick 必须 `WATCH_ONLY`，不能按旧 `entry_price` 买入；旧候选可保留作诊断，但不能进入生产持仓。
5. **A股 T+1 不等于禁止当天买入**：T+1 是买入后禁止同日卖出；若当日信号在交易时段产生，允许按实时价买入，但退出仍由 `t1_exit_allowed()` 约束。
6. **回测入场必须可成交**：`zone_limit` / zone price 若不在 entry_date 当日高低价内，不得视为成交。V88 的修复策略是标记 `execution_repair=ZONE_LIMIT_NOT_TOUCHED_USE_NEXT_OPEN`，改用原始 next-open 入场并重算 SL/TP/exit/PnL/RR/MFE/MAE。

## 必跑验证
- `python3 /root/.hermes/scripts/test_monitor_entry_execution_contract.py`
  - 覆盖旧候选不能 OPEN、交易时间用 live price、非交易时间 pending。
- `python3 /root/.hermes/scripts/v25/test_v88_executable_entry_contract.py`
  - 覆盖 V88 所有交易的 `entry_price` 均在 entry_date 当日 `[low, high]` 内。
- 继续跑原字段合同：`test_frontend_field_contract_mpkfagiawk77km.py`，确保 `/api/picks` 与 `/api/live-prices` 的选股日/加入日/Zone/成本线/波动仍为零空值。

## 关键修复点
- `/root/.hermes/scripts/smc_monitor_state.py`
  - `to_position()`：auto daily 不再因为 `contract_source` 锁定历史价；交易时段强制 live price。
  - `ingest_daily_picks()`：非交易时段进入 `NEXT_DAY_PENDING`，不直接 OPEN。
  - `fill_pending_orders()`：填单时再次用 live price 并重新跑 `production_entry_gate()`。
- `/root/.hermes/scripts/v25/v88_apply_production_contract.py`
  - 对不可成交 `zone_limit` 重算 next-open 合同，报告 `execution_repair_count`。

## 典型验收数字（本次修复）
- V88 trades: 532
- `execution_repair_count`: 73
- T+1 violations: 0
- field audit: 0 missing
- executable-entry audit: PASS
- monitor open rows: execution source 全部 `tencent_last`，5 月 OPEN 数为 0
