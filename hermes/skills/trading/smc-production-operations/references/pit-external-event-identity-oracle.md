# PIT 外部事件研究：部分历史范围、状态转移与冻结回放

## 边界

研究目标是验证策略本体，而不是等待所有数据完美齐备。若官方/PIT 数据来源隔离、时间戳可核验，且可用完整年份满足预设样本门槛，可在该范围内做 `research_only`；不得声称为全历史生产资格，也不得混源补洞。

## 固定流程

1. 冻结独立外部 PIT 事件和价格响应链；禁止用 PnL、MFE、MAE、exit 或未来 bar 选种子。
2. 对结果盲 seeds 先验收总数、逐年数、唯一证券数。
3. 独立 Oracle 重建外部事件、结构/POI/reclaim 和计划入场 identity。
4. Oracle 必须 `missing=0`、`extra=0`；否则冻结回放被阻断。
5. 仅在 Oracle 通过后执行一次严格 T+1 回放：entry 后下一根才允许退出、结构止损、入场前未消耗结构目标、RR≥1.5、stop-first、费用、串行持仓。
6. 若固定质量门槛或任一完整年份失败，关闭该本体，禁止参数/年份/选股变体。

## transition 状态的实现合同

对于截面分位触发的外部状态（例如 `lending_sell / prior_lending_balance >= q75`）：

- `transition` 只在今日 high 且昨日非 high 时出现；
- 零卖出、缺失强度或任何非 high 日都结束连续 high run；
- 不能只在证券从源文件消失时 reset 状态，否则会漏掉“高→非高→高”的真实再次进入事件；
- 若一只证券在不同外部事件下通往同一个 `planned_entry_date`，canonicalization 必须先定义并被 generator/Oracle 完全共享（本例：保留最早 external event）。

Oracle 发现差异时，先归因到：状态连续性、年度范围、canonicalization、结构锚点确认时间；修正明确定义错误后，必须重新生成 outcome-blind seeds 和 Oracle，而非在旧 seed 上继续回放。

## 已关闭实证例（不可重开变体）

官方融券卖出压力转高 → confirmed BSL acceptance → Demand POI reclaim → next-open：

- outcome-blind canonical seeds：46,092（2023=5,646；2024=17,528；2025=22,918）
- independent Oracle：46,092 expected / 46,092 actual，0 missing，0 extra
- frozen strict-T+1 replay：24,252 trades；WR 31.38%，AvgNet +0.0042%，PF 1.0014，payoff 2.19；2023/2024 AvgNet 为负；T+1=0

结论：外部融券压力未能识别可跨年、次日可执行的逼空承接。失败来自 hit rate 和年度稳定性，不是目标空间、数据不完整或 T+1 泄漏。不得改变卖空压力分位、响应窗口、POI、SL/TP、持有期、年份或证券子集。
