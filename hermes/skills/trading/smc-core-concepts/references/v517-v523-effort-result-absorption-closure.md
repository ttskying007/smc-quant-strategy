# V517–V523：Effort–Result Absorption 谱系更正与关闭

> **权威状态（2026-07-21 17:31 及之后）：CLOSED / FAIL-CLOSED。**
> 本文替换先前“V517 获得生产许可”的过期描述。完整对账文件：`/root/.hermes/smc_audit/v538_v517_lineage_reconciliation_and_frontier_closure_20260721.md`。

## 冻结因果对象

1. 3-left/3-right 已确认 swing low，且在 sweep 前已可见；
2. 后续 bar 下刺至少 0.3%，但收盘收回 low 之上；
3. sweep volume 位于之前 20 个完成 session 的 top quintile；
4. 下一根完成日线收盘突破 sweep high；
5. following-session open 才可入场，严格 A 股 T+1。

冻结执行：`stop=sweep_low×0.99`；目标为 entry 前已可见、且未被 response high 消耗的最近 confirmed swing high；出场从 entry 后首个交易日开始；SL-first；time20；费率 0.20%；单标的串行。

## 预注册晋级门禁

- outcome-blind support：总数 >=300、2023–2026 每年 >=40；
- 独立 raw-bar Oracle：种子集合零差异；
- frozen replay：WR >=55%、AvgNet >=+0.50%、PF >=1.15、payoff >=0.70；
- 样本量门禁按月：从第一笔至最后一笔已平仓入场之间，每个日历月均须 `n >4`；区间内的零交易月也失败，不得通过省略月度行隐藏。该样本量检查不再按年计算；T+1=0。
- 独立指标审计和 scanner-time contract 全部通过。

任一项失败，关闭本体；不得再调量比、窗口、SL、TP、hold 或年份/状态桶。

## 证据谱系

- V517 outcome-blind seed gate：406 seeds，年度 80/147/134/45，支持通过；
- V518 independent Oracle：406/406，missing=0、extra=0；
- 滚动 cache 先前快照曾输出 pass，但最终 latest 冻结重放为 381 closed，年度 67/146/129/**39**；
- 样本量稳定性不再使用年度门槛，而使用逐月 `n>4`：从第一笔至最后一笔已平仓入场之间逐个自然月检查，缺失月按零笔处理。须重新跑 V519→V520→V521→V522，才能以当前工件决定许可状态。

## 生产状态

- registry 必须为 `FAIL_CLOSED_REPLAY_GATE_FAILED`，`buy_enabled=false`；
- 所有历史/旧 pending 行都不得成交；当前 7 条 pending 已过期为 `EXPIRED_RESEARCH_GATE_FAILED`；
- 不存在 `BUY_VALID`、watchlist 写入或历史交易回填；
- 没有当前信号不是许可的替代品：V517 的**策略许可已撤销**。

## 研究治理

V517 的支持、Oracle 与当前 latest frozen replay 都已完成；失败根因为预注册年度已平仓样本门槛，不是未完成的调参任务。该日线量价对象已关闭。

只有获得新的 PIT 全历史全市场信息源（覆盖 >=95%），或同源全市场完整 2023–2026 分钟 OHLCV（15m=16、60m=4 每日 slots 全通过）后，才允许启动真正不同的新本体。