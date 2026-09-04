# V278 时间顺序组合/参数供给链审计教训

## 触发场景

当用户指出“交易量偏少”“每支股票应该有大量机会”“假定 SMC 原子指标没问题，剩下是组合指标和时间顺序参数”时，不要直接继续收紧生产过滤器，也不要只围绕 WR/RR 做表面调参。必须先做全市场供给链审计，拆开：原始事件密度 → 时间顺序组合 → 参数面 → 年度稳定性 → SL/TP/Time 出口结构。

## V278 全市场结论（2023-2026，4655只，no-write）

审计脚本：`/root/.hermes/scripts/v25/v278_sequence_combo_attrition_ultrafast.py`

主要产物：
- `/root/.hermes/smc_audit/v278_sequence_combo_attrition_ultrafast_no_write_20260702_173655/v278_summary.json`
- `/root/.hermes/smc_audit/v278_sequence_combo_attrition_ultrafast_no_write_20260702_173655/v278_parameter_surface.csv`
- `/root/.hermes/smc_audit/v278_sequence_combo_attrition_ultrafast_no_write_20260702_173655/v278_timeline_surface.csv`
- `/root/.hermes/smc_audit/v278_sequence_combo_attrition_ultrafast_no_write_20260702_173655/v278_per_stock_primitive_counts.csv`

原始 SMC 事件并不少：

| 原始事件 | 全市场总数 | 每股均值 | 每股中位数 | 每股90分位 |
|---|---:|---:|---:|---:|
| SSL sweep | 171,692 | 36.88 | 37 | 49 |
| BOS10 | 219,455 | 47.14 | 47 | 60 |
| BOS20 | 142,927 | 30.70 | 30 | 42 |
| BOS40 | 91,090 | 19.57 | 19 | 30 |

宽松 `BOS → 近端 Demand → 回踩/收复 → 次日入场` 任意参数组合去重后：

| 指标 | 数值 |
|---|---:|
| 唯一机会数 | 180,802 |
| 每股3年机会 | 38.84 |
| WR | 42.90% |
| Avg | +0.115% |
| SL占比 | 50.79% |
| TP占比 | 34.78% |
| T+1违规 | 0 |

最佳时间顺序参数面仍不够生产：

| BOS | Demand lookback | SSL窗口 | 回踩模式 | 等待 | n | WR | Avg | 年度最低WR |
|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 40 | 5 | 20 | strict | 3 | 1,356 | 49.19% | +0.570% | 42.86% |
| 10 | 8 | 20 | strict | 3 | 9,034 | 48.89% | +0.573% | 35.79% |
| 20 | 5 | 20 | strict | 3 | 4,106 | 48.76% | +0.568% | 37.50% |

时间顺序确实有弱增强，但远远不够：

| 时间关系 | n | WR | Avg |
|---|---:|---:|---:|
| 无 SSL 要求 | 180,802 | 42.90% | +0.115% |
| SSL_BEFORE_DEMAND | 155,174 | 43.76% | +0.189% |
| SSL_BEFORE_DEMAND + strict | 60,941 | 45.01% | +0.284% |
| SSL window 20 + strict | 29,300 | 45.91% | +0.380% |
| delay=5 + strict | 6,892 | 47.63% | +0.601% |

## 操作教训

1. **机会少不是原子指标少**：全市场原始 SSL/BOS 事件非常充足；如果生产候选少，要查组合语义和门禁，不要误判为扫描覆盖不足。
2. **不能把“最近一根阴线”当真正 Demand/OB**：这种写法会把系统退化为普通突破回踩，量很大但质量低。
3. **时间顺序参数只能小幅增强**：SSL 窗口、BOS lookback、Demand lookback、wait、reclaim mode 的网格搜索最多把 WR 从约43%推到约49%，不能把错误语义调成生产级。
4. **下一步应重建组合语法，而非继续扩大参数网格**：按 `Environment/Market State → Liquidity Event → Structure Shift → POI类型分离(真OB/FVG/OB+FVG) → POI质量/mitigation/zone death → Reaction → Entry` 重建。
5. **报告必须同时给“供给量”和“质量上限”**：用户关心每股机会密度，不能只报 top quality，也不能只报聚合 WR。

## 推荐审计流程

1. 全市场统计原始事件密度：SSL、BOS10/20/40、候选 demand/retest。
2. 统计顺序链路流失：BOS → demand20 → retest20 → executable entry。
3. 对 `BOS lookback × demand lookback × SSL window × reclaim mode × wait` 做参数面，但只作为诊断，不作为生产晋级依据。
4. 输出至少三张表：
   - 原始事件每股密度表
   - 参数组合质量表
   - 时间关系维度表
5. 若最优参数仍低于生产要求，明确停止调参，转向语义重建。