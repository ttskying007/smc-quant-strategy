# V34 LuxAlgo同源OB与止损归因（2026-05-22）

## 触发场景
当用户反馈“止损触发较多”，不要先调SL/TP。必须先拆分：信号定义、入场点、SMC组合、是否真正到入场点位、确认是否过期。

## 关键发现

### 1. 结构core必须先审计，不要假设旧core正确
V32 pivot-style结构与V34 LuxAlgo leg结构全量对比：

- V32结构事件：47,671
- V34结构事件：53,724
- 重合：32,375
- V32独有：15,296
- V34独有：21,349
- 约68%重合

结论：肉眼看到结构点不对时，先跑全量结构差异审计；不要用聚合WR证明信号正确。

### 2. 换结构core必须同步换OB生成
失败模式：LuxAlgo结构 + 旧V32 OB，会造成结构突破点和zone来源不同源，结果10笔/WR60%/SL40%。

正确做法：OB按LuxAlgo `storeOrderBlock()` 语义在结构突破发生时生成：

- bullish OB：从 crossed pivot bar 到 break bar 区间找最低 parsed low 所在K线；zone_low=low，zone_high=max(open, close)
- bearish OB：从 crossed pivot bar 到 break bar 区间找最高 parsed high 所在K线
- 交易引擎查OB时要求 `created_by_event_index == ev_idx`，禁止“附近旧zone”混配

代码位置：

- `/root/.hermes/scripts/v25/smc_core_luxalgo_v34.py`
- `/root/.hermes/scripts/v25/v34d_final.py`

### 3. 漏斗审计比直接回测更重要
全量4905只漏斗：

| 阶段 | 数量 |
|---|---:|
| MSS + SSL + 同源OB | 1151 |
| OB宽度合格 | 1115 |
| 结构后真实回踩OB | 481 |
| OB内确认成立 | 111 |
| 原二次limit入场成交 | 7 |

主要损耗：

- 634：结构后没有回踩OB或先失效 = 未到入场点位，不能追
- 370：回踩OB但无确认 = 入场确认不成立
- 104：确认后再等二次limit失败 = 执行模型过严
- 36：OB过宽 = zone质量差

### 4. 入场模型结论

| 模型 | 交易数 | WR | SL率 | 结论 |
|---|---:|---:|---:|---|
| 确认后再等二次limit | 12 | 66.7% | 33.3% | 过严，错过有效确认 |
| 确认K收盘入场 | 14 | 71.4% | 28.6% | 最优基础模型 |
| 次日开盘入场 | 15 | 60.0% | 40.0% | 延迟/追高增加止损 |

当确认K线已经在OB内完成rejection时，不应再要求第二次回踩；但次日开盘追入会恶化SL。

### 5. SL归因结论
V34B的SL交易平均risk_pct=2.96%，非SL=3.14%；止损不是因为SL太紧。

有效质量过滤：

- `zone_width_pct <= 2.0`
- `struct_to_confirm <= 20`
- 不禁RANGE：样本中RANGE 13/14，WR 76.9%，唯一TREND_UP反而SL

最终V34D：7笔，WR 85.7%，SL率14.3%，avg_pnl 2.19%。

## 以后处理“止损多”的固定流程

1. 全量结构core差异审计：旧core vs Pine/LuxAlgo语义core。
2. 检查zone是否与结构事件同源：OB/FVG必须能追溯到当前结构事件。
3. 做漏斗审计，而不是直接调SL：事件数 → sweep → 同源zone → 真实回踩 → zone确认 → 成交 → 退出。
4. 区分“未到入场点位”和“入场确认失败”：未回踩/先失效的信号必须丢弃。
5. 对SL逐笔归因：risk_pct、entry over zone、zone_width、struct_to_confirm、market_state、structure_label。
6. 再做过滤矩阵：优先测试过期确认、zone宽度、同源zone、执行模型；最后才考虑SL/TP。

## Pitfalls

- 不要把WR/RR当作信号正确性的证据。
- 不要只换结构core不换OB生成。
- 不要把“未回踩OB”的信号转成追高买入。
- 不要把确认K后的二次limit失败误判为信号失败；这是执行模型问题。
- 不要默认禁RANGE，必须用全量数据验证。