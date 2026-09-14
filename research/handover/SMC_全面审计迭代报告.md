# SMC A 股策略全面审计与迭代报告

## 1. 结论

本轮没有直接放宽生产阈值，也没有开启 SMC/CONT 实盘腿。先修复了会污染回测结论和生产诊断的确定性问题：

- 修复事件选股中 `limit_px` 在赋值前使用，避免合格事件触发 `UnboundLocalError`。
- 事件漏斗改为按 `(code, signal_date)` 记录唯一终态，区分事件腿订单和其他腿订单，支持守恒核对。
- 分类器异常改为 fail-closed，不再把无法分类的标题当成可交易事件。
- 回测与纸面退出统一双边滑点，TP1/TP2/TP3 按目标价成交，不再按盘中最高价虚构成交价。
- CONT 单目标达到 TP 后按 100%剩余仓位结算，不再固定只记 70%。
- 订单展示的 `tp_price` 改为执行内核实际消费的 `tp2`；`tp4`保留为研究层结构价。
- SMC 当前扫描拒绝历史 entry 追赶候选，避免以旧 entry 价在新日期成交。
- SMC 扫描结果增加短数据、陈旧数据、seed、阶段、R20、FVG 和历史 entry 拒绝诊断。
- 扫描结果明确标注当前 H 层是 `H_PROJECTED_DAILY`，不能误称真实 W-D-60m。

生产默认仍为：

```text
EVENT = enabled
SMC = disabled
CONT = disabled
paper/shadow only
```

## 2. 已确认的生产事实

### 2.1 选股数量少的根因

当前“少股/无股”不是一个阈值造成，而是多个漏斗叠加：

1. 默认只开启 EVENT 腿，SMC 和 CONT 即使产生研究候选也不会开仓。
2. EVENT 只查询公告库最近五个日期；公告延迟或库空会直接减少供给。
3. 标题分类会拒绝终止、减持、完成、进展、调整、注销、质押等标题。
4. EVENT 阶段只允许 `ACCUM`/`DOWNTREND`，并要求 ADX>=20。
5. 每个事件必须有对应 K 线及事件日期，缺失即拒绝。
6. SMC 需要至少 400 根 K 线、最新 bar 对齐、WDH seed、W permission、sweep、BOS、displacement、POI、确认和 FVG。
7. CONT 需要 MARKUP、近期支撑、低点回踩、VWAP 偏离 >=10% 和低波动。
8. 数据刷新失败、陈旧文件和候选容量限制都可能将最终订单数降为零。

现在 `current_scanner.py` 写出 `smc_diagnostics`，`paper_sim.py` 写出事件唯一终态，下一次真实运行可以区分“没有市场供给”“数据陈旧”“策略拒绝”和“组合容量拒绝”。

### 2.2 多周期事实

当前 WDH 不是完整的 W-D-60m：

- W 层提供方向许可。
- D 层提供结构和事件链。
- H 层在当前实现中使用日线投影语义。
- 60 分钟刷新脚本即使存在，也没有进入 `wdh_engine.build_seeds()` 的真实决策链。

因此当前结果必须标识为 W-D-H projected daily，而不是 W-D-60m。真实 60m 接入前，不能用“多周期确认”包装成更强证据。

### 2.3 时间顺序事实

已确认的正面约束：

- pivot 需要右侧确认。
- WDH 锚点需要早于 entry。
- CONT 的 signal 日只使用 signal 日及以前数据。
- EVENT 的量能比使用披露日数据，不读取未来 entry bar。
- T+1、开盘窗口、停牌、涨跌停和 pending TTL 已有统一守卫。

本轮额外关闭了 SMC 历史 entry 追赶路径。迟到 seed 只能进入研究回填，不能以历史 entry 价重新挂单。

## 3. 执行合同修复

### 3.1 回测与纸面

`research/core/execution.py` 现在对回测 `simulate()` 使用和纸面相同的滑点方向：

```text
买入价 = 计划入场价 × (1 + 单边滑点)
卖出价 = 目标/触发价 × (1 - 单边滑点)
净收益 = 分批滑点后收益 - 双边总费用
```

TP 触发判定仍使用盘中 high，但成交价使用目标价。这是保守且可复现的 limit/target 语义：盘中冲到目标不代表可以按更高的最高价成交。

### 3.2 退出计划

- `tp1`：部分止盈并移 SL 到保本。
- `tp2`：runner 实际全平目标。
- `tp3`：满足 runner 条件时的更高目标。
- `tp4`：仍可作为研究结构位，但不再作为当前 execution 内核的展示成交目标。
- 单目标 CONT：`tp1=None, tp2=目标价`，命中后 100% 剩余仓位结算。

### 3.3 事件漏斗

事件漏斗现在按唯一事件键保存一个终态：

```text
DATA_MISSING
STAGE_<stage>
ADX_LT20
BAD_CLOSE
BAD_SL_GE_ENTRY
CAPACITY_REJECT
PASSED_TO_ORDER
```

`conservation.mutex_check` 只对 EVENT 正事件集合核对，不再把 CONT/SMC 订单混入 EVENT 漏斗。

## 4. 当前自适应能力边界

`research/core/adaptive.py` 已有基于过去窗口 ATR 的波动档位和参数解析：

- low / mid / high 波动档。
- sweep 容差。
- displacement ATR 门槛。
- SL ATR 缓冲。
- max hold。

`research/core/profile.py` 也已有股票画像和共享参数族研究实现，包含波动、跳空、趋势持续、噪声、扫损深度、位移、FVG/OB 反应和典型持有期等字段。

但这些模块目前主要由研究脚本和单元测试使用，尚未成为 EVENT、SMC、CONT 三腿的生产统一参数源。这个边界必须保持透明：

- 已有“画像计算能力”。
- 尚未完成“生产决策接入”。
- 尚未在当前生产合同下完成真实数据 walk-forward 验证。
- 因此本轮不把自适应参数直接升格为实盘默认。

## 5. 后续至少五个迭代方向

### 方向 A：真正的 W-D-60m 因果链

目标：将 60m 数据按交易日和信号时刻聚合，替换 `H_PROJECTED_DAILY`。

要求：

- 60m bar 必须有 source timestamp 和交易日。
- 日线信号只能消费信号时刻之前已收盘的 60m bar。
- 盘中未收盘 bar 不得用于 displacement、FVG、reclaim 或 entry。
- 对同一信号运行 daily-projected 与 true-60m A/B。

验收：截断到时点 T 的结果不能被 T 之后的数据改变；逐笔记录 H 层最后可见 bar。

### 方向 B：个股画像驱动参数

目标：将 profile/adaptive 接入统一 ExecutionPlan，而不是在各脚本中各算一套。

可调参数：

- sweep 容差。
- displacement 最低强度。
- POI 宽度和容忍度。
- SL 结构缓冲。
- TP 阶梯和最大持有 bar。

约束：参数只使用决策时点前窗口；样本不足回退到共享族；每笔订单记录 `profile_version`、`parameter_bucket` 和实际参数。

验收：purged walk-forward 中自适应臂需在多数窗口改善风险调整收益，且不能只靠交易数量增加获胜。

### 方向 C：结构腿与事件腿的因果组合

目标：不再把 EVENT、SMC、CONT 作为简单并列循环，建立统一候选对象：

```text
candidate_id
source_legs
signal_time
valid_from
expiry
structure_score
event_score
regime_score
execution_plan
```

同股同日的多腿信号应合并为一个候选，记录互补证据和冲突证据，避免重复占用容量。

验收：组合排序必须只使用 signal_time 之前字段；比较单腿、并列腿和统一评分三种结果。

### 方向 D：Smart Money 证据分层

目标：把“聪明钱”从单一标签拆成可审计证据：

- liquidity sweep。
- displacement。
- BOS/CHOCH。
- FVG/OB 位置。
- reclaim/retest 顺序。
- 量能和相对波动确认。

每个证据保存发生时间、父事件和失效时间。任何乱序或时间回归都拒绝。

验收：每个候选能还原完整事件链；随机打乱未来列不能增加当前信号。

### 方向 E：自适应 POI、入场和 TP/SL

目标：从固定比例和单一结构价改为结构加波动联合计划：

- POI 区间由 OB/FVG/摆动池生成。
- entry 使用区间内可成交价格，区分 strict limit 与 limit-or-open。
- SL 位于结构失效点外并受 ATR 缓冲限制。
- TP 使用风险倍数和前方流动性池共同约束。
- 记录 expected R、实际 R、MFE、MAE 和退出原因。

验收：逐笔对账回测、paper 和 shadow 的 fill/exit/pnl；成本压力测试后仍需通过 PF、回撤和稳定性门槛。

### 方向 F：零信号漏斗与机会成本

目标：对每个拒绝阶段记录被拒候选的未来 5/10/20 日收益，而不是只统计通过数量。

比较：

- 当前 strict gate。
- 单项放宽 ADX。
- 单项放宽 VWAP。
- 支撑年龄 5 到 7。
- 同股冷却期。
- 保留研究级进展事件。

每项只能在固定 OOS、bootstrap 区间、成本模型和容量约束下比较，不能因“数量变多”直接放宽生产。

### 方向 G：真实交易约束和市场状态

补齐并统一：

- ST 5%涨跌停。
- 停牌、跌停无法卖出。
- T+1。
- 开盘窗口。
- 跳空。
- 行业和组合暴露。
- 市场 regime 只影响已有候选的风险，不凭空制造信号。

## 6. 回测审计循环

每个版本按以下顺序执行：

1. 固定代码、配置、成本和数据快照 hash。
2. 生成事件腿、SMC 腿、CONT 腿各自漏斗。
3. 生成统一候选和 ExecutionPlan。
4. 运行训练/OOS/walk-forward，按腿、月份、市场状态和行业分层。
5. 对账 fill_price、exit_price、reason、hold、gross、fee、net。
6. 运行压力测试：滑点、费用、涨跌停、停牌、延迟、缺失数据。
7. 只有通过稳定性门禁才进入 shadow；shadow 观察期通过后才讨论生产开关。

## 7. 测试结果

已执行：

- `python -m compileall -q research wdh`
- `python -m py_compile research/paper_sim.py research/core/execution.py research/current_scanner.py`
- `for f in research/tests_*.py; do python "$f" || exit 1; done`
- `git diff --check`

结果：全量测试命令退出码为 0；执行合同、因果时序、枚举、组合、画像和安全门禁测试均通过。缺少本地行情/指数缓存的测试按项目既有规则 `SKIP`，不能视为真实行情回测通过。

## 8. 尚未解决的事实缺口

- 当前工作区没有生产行情缓存，无法重跑最近一个月真实选股漏斗。
- 没有完整公告刷新产物、paper ledger、shadow ledger 和运行级 manifest，无法证明最近一次线上运行在哪一层丢失候选。
- 没有真实 60m 决策链，不能给 W-D-60m 结论。
- adaptive/profile 还没有在当前生产合同下完成 OOS 晋级。
- SMC 历史回测中已有负向或不稳定证据，默认继续关闭是有意的风险控制。

## 9. 生产建议

在补齐真实数据和完成新基线前：

- 继续 paper/shadow，不开启实盘。
- 保持 `SMC_ENABLE_SMC_LEG=0` 和 `SMC_ENABLE_CONT_LEG=0`。
- 每次运行优先检查 `run_status.json`、`run_transaction.json`、`selection_result.json`、`selection_funnel.json` 和 `current_scanner_result.json`。
- 任何阈值放宽必须以新版本号、固定 OOS 和可回滚配置发布。
