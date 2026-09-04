---
name: causal-trading-research
description: 以结果盲信号、独立 oracle、冻结严格 T+1 回放和机制归因为核心的可审计 SMC/成交量策略研究。适用于研究、验证或晋级交易信号体系，防止未来函数与事后过滤。
user-invocable: true
metadata:
  category: trading
  tags: [smc, causal-inference, backtest, t+1, volume, signal-research, audit]
---

# 因果交易研究与策略晋级

## 适用范围

用于验证或研究 SMC、成交量、市场结构、流动性、FVG、OB 等**信号体系**；不是用于给既有回测加事后筛选来改善数字。目标是判断机制是否可用，或明确关闭不可用对象。

## 不可违反的原则

- 结果盲：种子生成阶段不得读取 entry 后价格、收益、止损、目标、交易记录或标签。
- 单源：同一研究对象的价格、成交量、结构和回放必须标识来源；不得静默混用不同供应商的序列。
- T+1：A 股 entry 当日不得退出；同 bar SL/TP 碰撞按保守 SL-first。
- 生产候选与历史回测严格分离；失败对象不得回填历史交易为实时候选。
- 不用事后优胜的标的、月份、时段、RR 或分桶直接作为新生产门禁。

## 标准研究闭环

1. **预注册假设与可用门槛**
   - 用一条可反驳的机制表述，而不是“找到高胜率”。
   - 在打开新结果前固定：样本下限、分年样本下限、胜率、平均净收益、PF、payoff、逐年正收益、T+1 零违规。
   - 定义失败即关闭：任一硬门槛不达标，不能通过切片挽救。

2. **生成结果盲 seeds**
   - 逐 bar 状态机只访问当前 bar 及此前已确认的信息。
   - 每个 identity 写入 symbol、关键结构事件时间、entry_time、原始机制特征；entry 必须严格晚于确认事件。
   - 输出时断言不存在 `pnl`、`return`、`stop`、`target`、`exit` 等结果字段。

3. **独立 oracle**
   - 用独立状态机/实现重算同一身份集合；不要共享生成器状态。
   - 比较 identity 集合与时间顺序，而不是只比较总数。
   - 不一致时先关闭或修正种子定义；不得进入回放。

4. **单一冻结回放**
   - 回放前冻结：entry、结构止损、只使用 entry 前可见且未被消耗的结构目标、费用、最长持仓、重叠仓位、碰撞顺序。
   - 对移动窗口缓存，必须通过不可变 trading date/time 重绑定事件，不能复用陈旧 array index。
   - 输出逐笔可审计日志：选股日、T+1 买入日、entry、SL、结构 TP、计划 RR、exit、原因、PnL、持仓 bars、MFE/MAE、T+1 断言。

5. **机制归因，然后才允许新假设**
   - 失败时统计：SL/GAP_SL/TP/TIME exit、MFE/MAE 相对 R、目标触达率、风险与目标距离、年份、时段、时序、标的集中度。
   - 归因必须回答“哪个机制失效”，不能把表现好的切片当作结论。
   - 新研究应只改变一个可解释机制，并重新开始结果盲 → oracle → 冻结回放链。

## 先确认历史 Swing 锚点，再判定 Sweep

当语义是“已确认 Swing Low 之后的 Sweep”时，禁止用 `swing_idx = sweep_idx - right - 1` 把它偷换成固定间隔模式。应从 Sweep 前所有已完成右侧确认的 Swing Low 中，排除已被介入 bar 消耗的流动性，按预注册的最近有效锚点规则做 canonicalization，并输出完整锚点溯源。

这属于**语义修复**而不是参数修改：修复后，原 seed、Oracle、冻结 replay、指标审计、scanner 和前端字段均失效，必须从结果盲种子开始全链重跑；若唯一冻结 replay 未通过既定门禁，关闭本体，禁止以窗口、阈值、止损、目标、持有期、年份或子集变体救回。详细的检测、重跑顺序和断言见 `references/prior-confirmed-canonical-sweep-anchor.md`。

## 数据不完整时的策略探索边界

当已关闭的技术本体需要由一个**新日内数据维度**重新开启时，先执行来源资格审计：最大窗口的 SH/SZ/BJ 代表探测 → 全市场 universe/slot/时间戳/日线聚合审计 → 才能授权一个新本体。短历史滑动窗口和跨源补齐都不能替代这一步；详见 `references/full-history-intraday-source-qualification.md`。

数据不完整不等于策略研究结束。若存在完整、可复现的一至两年可用范围，应在明确范围、保持单源与严格 PIT/T+1 合同的前提下继续 no-write 策略研究；`EMPTY_BOOK` 仅限制生产写入，**不是以数据资格审计替代策略探索的理由**。

- 对部分历史，先固定双层门槛：研究支持门槛（通常总 unique identities>=1,000、每可用年>=300）与策略质量门槛（n、每年样本、WR、AvgNet、PF、payoff、逐年正收益、T+1）。
- 支持不足时关闭的是**该具体本体**，不得为了打开回放而放宽它的 Swing/CHOCH/时窗条件。
- 支持与 Oracle 都通过、但冻结回放失败时，同样只关闭该本体；高 PF/payoff 或单年正收益不能掩盖 WR/AvgNet 失败。
- 下一步必须转向解释“为什么信号能跨越 T+1 隔夜仍持续”的独立因果机制，不能修改已关闭本体的窗口、阈值、SL/TP、持有期、年份或标的切片。

部分历史下行业父级结构→个股 M15 子级结构的完整正反例见 `references/partial-history-parent-child-mtf-research.md`；通用边界见 `references/strategy-goal-over-data-completeness.md`。对“早盘行业参与不等于个股午后接管”、逐阶段样本门槛和结构存活新本体的复用模式，见 `references/partial-history-midday-survival-research.md`。对“日线结构 → 精确 M15 CHOCH → 同刻行业广度/成交额/个股参与”的结果盲横截面本体、午休 slot、身份 canonicalization 与失败关闭规则，见 `references/exact-bar-industry-volume-takeover.md`。对于公告类 PIT 外生信息，先审计目录覆盖与发布时间，再预注册事件词表和结构链；完整支持/Oracle 不等于经济可用，示例与关闭规则见 `references/pit-event-ontology-validation.md`。当已审计的本体均已关闭时，必须停止对旧本体做变体迭代；仅能先对新的独立数据源进行无结果资格审计，再决定是否授权新本体，详见 `references/frontier-closure-and-source-only-reopen.md`。事件语义必须由源字段证明；不同事件状态不得偷换为 selector；支持不足、语义不足和冻结回放经济失败均须 fail-closed，详见 `references/pit-event-semantics-and-closure.md`。当事件依赖公告原文或公司行动数值条款时，还必须审计逐公告身份、正文哈希、官方附件恢复、事件时点可观察性及支持失败关闭边界，见 `references/pit-raw-terms-and-support-gate.md`。对限流型分页源的断点续建、供应商 canonical filter 提取、**事件身份粒度必须由源数据证明**（URL vs (secucode,notice_date) 1:1 判定，勿用 receive 窗口拆分披露）、列序重构解包陷阱、AN ID→公告正文独立验证，以及结果盲种子合同，见 `references/pit-source-build-identity-and-validation.md`。

## SMC 反转状态机：先做语义验收，再授权回放

对于 `SSL sweep → CHOCH/MSS → displacement → OB/FVG → retest` 的反转对象，不能在 seeds 生成后直接做 Oracle 或回放。必须先运行完整、结果盲的三层状态机语义验收：已确认 SSL 与 sweep、只包含 reversal 的结构接管、因果 displacement-OB/FVG，以及 `FRESH → FIRST_TOUCH → RECLAIM → HOLD → next-bar` 的单向 POI 生命周期。

- 输出只允许 `VALID_CHAIN`、`CANCELLED_CHAIN`、`EXPIRED_CHAIN`；首次 touch 无 reclaim 或跌破 zone 必须终止，后续不得复活。
- 每个 symbol 仅允许一条 active chain，且 `symbol + entry_date` 必须唯一；新 sweep 应取消旧链。
- 先机械断言 pivot 可见性、事件时间序、OB 不在 break bar、首次触及不可重用、BUY 无重复；再导出三类 OHLC 样本作逐链核验。语义验收通过也**不等于**已获回测授权。
- 完整字段、规则与样本导出边界见 `references/reversal-state-machine-semantic-acceptance.md`。
- 生成器自检后必须用独立 raw-bar witness 覆盖 pivot 可见性、严格早于 sweep 的 reference-high 确认、CHOCH 首次性、causal OB、first-touch/hold 及取消状态语义；具体断言与取消原因 taxonomy 见 `references/reversal-state-machine-raw-witness.md`。

## 多周期趋势路由 → 低周期入场

当低周期信号既承担方向又承担入场而表现不稳定时，不要把它当作止损或阈值问题。可将**父级趋势路由**作为独立机制预注册：`已完成周线趋势 → 已完成日线趋势 → 低周期 sweep/displacement/reclaim → 下一可成交 bar`。

- 父级趋势只用于方向/环境，不得偷用入场日尚未收盘的日线信息。
- 周线/日线 pivot 必须以右侧确认时点计入可见性；每笔 seed 都要断言父级确认严格早于低周期 entry。
- 先运行 outcome-blind 支持门禁；样本不足时不得放宽趋势、窗口或量能条件来打开回放。
- 这是一种新层级因果本体，不能被既有“周线事件→日线入场”或“裸 15m 入场”研究的结论替代。

详见 `references/htf-trend-ltf-entry-support-gate.md`。

对于周线→日线→60m 的 POI 接管链，除 pivot 可见性外还必须逐 bar 断言 W1 和 D-POI 到实际 entry 的**持续有效性**，并将 next-open 的结构止损可行性作为实时订单条件；冻结失败后只能做不读结果字段的生命周期归因。若同一 sweep bar 可 raid 多个 liquidity pool，必须在预注册中定义唯一 pool 或把 pivot 纳入独立 chain identity；identity exact match 后还必须在回放前检查完整结果盲 universe 的支持门槛。详见 `references/persistent-mtf-lifecycle-closure.md` 与 `references/multitimeframe-lifecycle-identity-and-support-gates.md`。

## SMC + 成交量的可检验新机制

当纯价格链 `SSL sweep → BOS → FVG → reclaim` 出现大量结构止损、跨年退化或目标兑现不足时，可研究而非直接采用以下四阶段机制：

`高参与度扫取流动性 → 放量/位移 BOS 与 FVG → 缩量回测吸收并 reclaim → 下一根未观察 bar 入场`

所有成交量分位、波动倍数、允许 bars 和入场规则必须在结果盲阶段固定。不要因为某个结果分桶看起来较好才选择阈值。

## 活跃链路与发布门禁审计

在诊断“当前前端/生产策略为何异常”前，必须先以运行证据而非旧文件名确定活跃链路：服务 entrypoint、目标页面/API 所用 adapter、production registry、当前 scanner artifact，以及该表面是研究、生产还是 `EMPTY_BOOK`。旧 engine 常量、历史 trade 文件或 archive 不得被误认成当前研究本体。

冻结 replay 的发布门禁必须同时在 replay 和 release aggregation 中检查：总样本、每个预声明年份的最低样本、每年 `AvgNet > 0`、完整区间的月度支持、整体 WR/AvgNet/PF/payoff 与严格 T+1=0。release aggregation 必须独立复查逐年字段；字段缺失一律 fail-closed。补足遗漏的安全门禁不授权重跑、改合同或挽救已关闭本体；只能保留 frozen artifact 并做 no-write 的许可复核。

会话级复现与检查清单见 `references/active-lineage-and-release-gates.md`。对冻结失败后的只读归因、研究前端与遗留路由分离、以及 `PENDING_NEXT_OPEN` 当前 epoch 原始身份复算，见 `references/frozen-chain-frontend-and-current-epoch-audit.md`。

## 验收清单

- [ ] Seeds 无结果字段、entry 晚于所有确认事件
- [ ] Oracle identity 集合一致
- [ ] 全部 entry/target/stop 均可在当时获得
- [ ] 所有 A 股回放 T+1 违规数为 0
- [ ] 分年门槛和整体门槛同时通过
- [ ] 没有把历史 trade 文件作为当前 watchlist
- [ ] 若失败，已有机制归因和明确关闭结论

## 参考

- `references/causal-signal-research-gates.md`：V541–V543 可复用的冻结回放、性能优化和失败归因模式。
