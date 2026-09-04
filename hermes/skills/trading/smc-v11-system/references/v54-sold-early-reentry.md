# V54 SOLD_EARLY 拆分与再入场机制

## 触发场景

当 90D 闭环复盘出现大量 `SOLD_EARLY_NEXT_90D` 时，不要默认通过继续延长原始持仓解决。必须先把“卖早后又涨”拆成两类：

1. **原 setup 主升段没吃完**：属于 runner/结构出场问题。
2. **exit 后形成新 SMC setup**：属于遗漏二次机会，应该重新入场，而不是原单死拿。

第三类是 exit 后很久的漂移行情或没有可执行 setup，不应强行优化。

## 核心教训

`SOLD_EARLY_NEXT_90D` 不是单一出场问题。部分后续涨幅来自原交易 exit 后很久的新结构，而不是原始 setup 的连续主升段。继续强行延长持仓会增加利润回吐，且不一定提高捕获率。

因此处理顺序必须是：

1. 先逐笔分解 SOLD_EARLY：
   - `A_ORIGINAL_RUNNER_MISSED`
   - `B_NEW_SMC_REENTRY_MISSED`
   - `C_LATE_DRIFT_OR_NO_EXECUTABLE_SETUP`
2. 只有 A 类才改 runner/结构出场。
3. B 类要做 post-exit reentry。
4. C 类不应为提高指标而交易。

## V54 实现形态

在 V53 趋势分层 runner 逻辑上叠加再入场，不改变原始交易出场规则。

推荐字段：

```python
trade_role = "REENTRY"
reentry_from_trade_id = original_trade_id
reentry_reason = "POST_EXIT_NEW_SMC_SETUP"
source_event_idx = new_signal_idx
zone_idx = new_zone_idx
retrace_index = new_entry_idx
conf_index = new_confirmation_idx
```

REENTRY 是独立新交易，不是原交易续持。因此：

- 不强制与原始交易的 `retrace_index` 顺序递增；
- sequence audit 应跳过 REENTRY 的原始 retrace 顺序检查；
- 但仍必须验证 `source_event_idx <= conf_index <= retrace_index <= exit_index` 等本交易内部时间顺序；
- K线图表必须能同时显示原始交易与 reentry 交易。

## 再入场候选条件

V54 使用的保守形态：

- 在原交易 exit 后窗口内扫描；
- 只接受新的 bullish SMC setup；
- 可用 setup 家族包括：
  - `Sweep_SSL`
  - `CHOCH_Bull`
  - `BOS_Bull`
  - bullish structure 家族
- 必须方向一致；
- zone 与后续 K 线价格范围存在可执行重叠；
- 必须有确认信号与实际入场 K 线；
- 质量门槛独立评估，不因原交易盈利而自动放行。

## 审计要求

新增版本时必须同步生成和运行：

- quality metrics
- trade provenance audit
- signal sequence audit
- closed-loop 90D review
- sample bias audit
- monitor journal
- release gate

如果 sequence audit 直接复制旧版本，必须专门处理 REENTRY：跳过“必须晚于原 retrace”的跨交易检查，但保留本交易内部时序审计。

## 前端同步要求

新增 V54/Vxx 版本时必须同步：

- `ACTIVE_VERSION`
- active trade/pick/report 文件路径
- `get_version_trades()`
- `get_version_picks()`
- `_active_version_paths()`
- API `ver` 参数映射
- 回测页版本列表
- 选股页版本列表
- K线页版本列表
- autopsy 版本映射
- HTML 下拉默认值

验证端点至少包括：

```bash
/api/summary
/api/picks/contract
/api/picks
/api/kline_full?symbol=<symbol>&tf=daily&ver=V54
/autopsy
/live
```

## 成功标准

不能只看 `SOLD_EARLY_NEXT_90D` 数量，因为新增 reentry 交易本身也会进入 90D 复盘，强势股可能继续被标记为卖早。应同时看：

- `avg_pnl`
- `avg_realized_r`
- `profit_loss_ratio`
- `avg_90d_capture`
- `LOW_90D_MFE_CAPTURE` 占比
- reentry 子集胜率和平均收益
- release gate 是否通过

重点是收益质量是否改善，而不是机械消灭所有 SOLD_EARLY 标签。
