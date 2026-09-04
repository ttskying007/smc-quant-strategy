# SMC 实盘交易 SL 复盘：样本污染 vs 信号/入场/风控归因

## 触发场景
用户要求“先不进行任何调整，分析历史几笔交易为什么基本全部 SL，是信号问题、入场问题还是底层逻辑问题”。此类任务必须只读诊断，不得顺手修改代码、策略、持仓或前端。

## 必须先分清样本类型
不要把所有 closed_reviews 都当成“当前生产信号质量”。先按下面字段分层：

- `pick_date/select_date/entry_date`：信号产生日/选股日。
- `created_at/buy_date/joinDate`：进入监控或实际买入日。
- `source/pick_scope/is_active_pick/engine/definition_version`：是否来自最新全市场扫描。
- `raw_pick.zone_low/zone_high/zone_idx/conf_index/source_event_idx`：是否有完整 SMC 溯源。
- `execution_price_source/entry_price`：是否真实实时价，还是历史 pick price。

硬规则：

1. `buy_date - pick_date > 7` 天的样本标记为 stale，不可直接评价当前信号。
2. `buy_date - pick_date > 30` 天的样本标记为 very stale，主要用于暴露监控污染/执行问题。
3. 缺 `zone_idx/conf_index/source_event_idx` 且 zone 为 0/空的样本标记为 `NO_PROVENANCE_ZONE`，不可声称“SMC zone 信号已验证失败”。
4. created_at 集中在同一时间、pick_date 分散在几个月前，通常是历史候选/历史最佳批量导入污染。

## 逐笔复盘指标
对每笔 closed review 计算：

- `lag_days`, `lag_bars`：选股到买入延迟。
- `entry_vs_buy_close%`：记录入场价与买入日真实K线/实时价差异。
- `zone_distance%`：入场价相对 `zone_low~zone_high` 的距离。
  - 在 zone 内：正常。
  - Bull zone 下方明显偏离：可能 zone 已跌破/失效，不能继续按 demand 买。
  - Bull zone 上方明显偏离：可能追高。
- `SL%`：`(entry - sl) / entry`。
- `MFE/MAE`：买入后到关闭前最高浮盈/最大不利波动。
- `SL_GAP_OR_OVERSHOOT`：MAE 明显超过 SL 宽度，说明被跳空/波动放大打穿。
- `HAD_MFE_BEFORE_SL`：SL 前曾有 >2% 浮盈，说明未必是方向错，可能是利润保护/出场生命周期问题。

## 归因模板
按层级归因，不能只说“信号错”或“止损太小”：

| 层级 | 判断标准 |
|---|---|
| 样本污染 | stale、very stale、批量导入、历史候选混入实时监控 |
| 信号问题 | zone/confirm 本身不成立、FVG/OB 与结构点不一致、raw provenance 能证明信号无效 |
| 入场问题 | 当前价偏离 zone，跌破 zone 后仍买，或远高于 zone 追高 |
| 风控问题 | SL 为固定百分比而非结构失效位；MAE/ATR 与 SL 不匹配 |
| 出场/生命周期问题 | MFE 明显为正后最终 SL，说明缺利润保护或结构延续/失败判断 |
| 执行问题 | entry_price 沿用历史价、实时成交价缺失、created_at 与 pick_date 大幅错位 |

## 报告口径
先给结论排序，再给表格证据：

1. 样本是否干净。
2. SL 是否集中在 stale/no_zone 样本。
3. 新鲜样本中入场与 zone 的距离。
4. SL 是结构失效还是固定百分比。
5. MFE 是否说明信号方向曾经有效。
6. 最终一句话：信号、入场、风控、执行各自占比/主因。

## 重要教训
历史 closed_reviews 里的 TP/SL 都可能被历史候选污染。大 TP 不一定证明策略强，大 SL 也不一定证明当前信号错。必须先隔离“最新全市场扫描产生的 active candidates / watchlist 实盘样本”，再评价生产信号。