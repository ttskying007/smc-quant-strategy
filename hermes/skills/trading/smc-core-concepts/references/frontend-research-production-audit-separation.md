# SMC 前端：研究、生产与历史审计的三层分离

## 适用场景

策略处于 `EMPTY_BOOK`、研究 Shadow 或未生产晋级时，用户仍需要核验历史交易、K线信号和止盈止损，而不能把任何历史行写回当前选股或仓位。

## 三个不可混淆的数据面

| 数据面 | 可展示 | 禁止 |
|---|---|---|
| 当前生产候选 | committed scanner epoch 的 ACTIVE/PENDING/SHADOW 状态与 0 候选 | 从历史交易文件回填候选、写 watchlist/仓位 |
| 冻结研究 replay | 全部逐笔交易、因果节点、T+1、SL/TP、结构目标、出场和指标 | 标记为 BUY 或用作实时选股 |
| 旧系统 artifact | 信号、组合合同、入场/SL/TP/RR、出场/PnL 的只读审计 | 作为当前策略绩效、当前候选或生产数据 |

UI 标签必须明确使用 `REPLAY_ONLY`、`HISTORICAL_ARTIFACT_ONLY` 或 `NOT_CURRENT_PICK`。

## K线展示合同

一个可审计 K线页应同时显示：

1. Pine-like/同源 SMC **视觉上下文**：已确认 swing、OB、FVG、Sweep、BOS/CHOCH、OTE、EQL 等；
2. 策略自己的因果节点与时间序列；
3. 实际 BUY、SELL、SL、TP 水平线；
4. 逐笔合同：组合、信号日、严格 T+1 买入日、入场价、SL 的结构依据、TP 的结构依据、计划 RR、实际出场与 PnL。

视觉上下文必须标成 display-only，不能将图上的任一 OB/FVG 自动解释为该研究策略的入场条件。

## 结构 SL/TP 不能替代经济门禁

即使 SL 与 TP 都来自可见 SMC 结构，仍逐笔计算：

```text
planned_rr = (structural_target - entry) / (entry - structural_stop)
```

若生产合同要求 `planned_rr >= 1.5`，必须报告全体、通过数、通过率、中位数与分布；任何未通过者不能被“结构目标”标签掩盖。不要为了满足阈值在冻结 replay 上直接把 TP 拉远；那是新执行合同，必须以 outcome-blind 规则重建并做独立、全市场、严格 T+1 验证。

## 最小验收

```text
GET sample research Kline
assert SMC context signal count > 0
assert BUY/SELL/SL/TP all appear for replay trade
assert kline contract exposes combo + T+1 + planned RR
GET current selection: no historical rows treated as ACTIVE
GET research replay: all frozen rows visible
GET legacy audit: rows visible and explicitly quarantined
assert production write endpoints remain fail-closed in EMPTY_BOOK
```
