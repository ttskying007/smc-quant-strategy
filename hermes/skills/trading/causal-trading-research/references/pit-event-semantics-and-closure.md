# PIT 事件语义、支持门禁与关闭规则

## 适用场景

对公告、融资融券、质押、回购、限售、持股变动等外生事件研究 `PIT event → SMC response → T+1 execution` 时使用。本参考记录的是可复用方法，不是任何具体事件的生产结论。

## 先做事件语义，再生成价格种子

1. **事件目录只读**：先冻结 `symbol / announcement_id / notice_date / publication_time / title / event_kind`；禁止在这一步读取行情、收益或回测文件。
2. **语义必须可由源字段证明**：标题元数据不能证明盈利预增、盈利幅度、资金规模或实际执行状态时，不得把它臆测为正/负事件。需要事件正文或结构化数值字段，并验证其发布时间。
3. **同日禁用**：公告日不能被当作响应、确认或执行日；所有价格反应从后续可完成交易日开始。
4. **事件类型不可偷换**：如“质押创建”与“质押解除”是不同风险状态。一个失败后只能关闭该事件本体，不能把另一类型作为同一本体的 selector 变体。

## 结果盲支持门禁

在打开任何 exit/target/PnL 之前：

- 每个事件先生成完整、结果盲的因果链；例如 `事件 → 已确认流动性锚 → sweep/acceptance → 已确认结构突破 → 固定 POI → reclaim → 下一交易日开盘`。
- Pivot 的右侧确认必须在 sweep 或 break 前完成；POI 必须在 retest 前固定。
- canonical identity 至少应包含：`symbol, event_date, announcement_id, anchors/confirm dates, sweep/break date, poi date, reclaim date, planned_entry_date`。
- 先按 `(symbol, planned_entry_date)` 去重，随后检查总种子、每完整年度种子和独立股票数。支持不足时关闭本体，不能放宽时窗、结构或事件词表以打开回放。

## Oracle 与冻结回放

- Oracle 必须用独立 pivot/状态实现从原始事件和 OHLC 重建 identity 集合；只比较集合不比较聚合数量。
- 身份完全一致后，才允许一次冻结执行：下一日开盘、预先可见且未消耗的结构目标、结构止损、费用、T+1、保守 stop-first collision、固定最大持仓和串行同标的持仓。
- 独立指标审计还必须重算按年和总体的 `n / WR / AvgNet / PF / payoff`，并验证 chronology、RR、执行合约与 T+1。

## 失败解释

`Oracle 一致 + T+1=0 + 结构目标均为入场前已知` 只说明研究无泄漏，不说明策略有优势。若 WR、AvgNet、PF 或逐年稳定性未达到预注册门槛，应归因为**经济失败**；禁止再做 selector、时窗、止损、目标、持仓期、年份或股票子集变体。

## 元数据研究前沿

在已有公告档案中寻找下一事件族时，先做 metadata-only 分类：

- 原始事件或 canonical seeds 未达到总量/分年支持门槛：不进入价格种子和结果回放。
- 已经被一次冻结回放关闭的事件类型：不复开变体。
- 事件标题无法表达所需经济方向或幅度：标记为 `NOT_SEMANTICALLY_IDENTIFIABLE_FROM_METADATA_ONLY`，需要新的 PIT 字段，而不是标题规则调参。

这能避免把“数据目录探索”误当作策略优化，也能确保数据不完整时仍优先寻找真正独立的因果维度。