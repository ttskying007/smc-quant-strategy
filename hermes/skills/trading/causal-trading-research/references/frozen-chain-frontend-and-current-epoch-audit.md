# 冻结策略链：失败归因、前端版本与当前 epoch 审计

适用于已经完成 `outcome-blind seed → independent Oracle → exactly one frozen strict-T+1 replay` 的策略链。

## 不把失败诊断变成事后策略

冻结回放失败后，允许逐笔诊断：年度/月度覆盖、SL/GAP_SL/TIME/TP 结构、MFE/MAE、信号/入场/结构目标的时序与市场状态归因。禁止把表现较好的年份、标的、实体强度、延伸幅度、RR、止损、目标、持仓时长或事后分桶回写成同一 ontology 的新过滤条件。

诊断应输出：

- 是语义/机制失效、执行时序失效、风控几何失效，还是数据/PIT 失效；
- 支持该裁定的原始逐笔字段和分年证据；
- 明确说明分桶仅用于定义下一独立本体的假设，不能“救回”冻结对象。

## 生产界面与研究版本分离

`EMPTY_BOOK`、`production_strategy=null` 或遗留路由变量不等于当前研究前端回退。必须从实际 adapter/import、页面标签和 API payload 确认研究版本；同时从 production registry 确认买入许可。

报告应分别写出：

1. 当前研究/可视化 ontology；
2. 冻结回放与 release gate 状态；
3. production registry 的 `buy_enabled`、`active_buy_valid_count` 与 fail-closed reason；
4. 历史回放交易是否被禁止作为 current candidate 来源。

## 当前 scanner row 的真实性

对一个 `PENDING_NEXT_OPEN` 当前候选，使用**同一 committed epoch 的原始 K 线**独立重算：已确认摆点、未消费流动性、sweep/reclaim、量能排名、response、预先可见 target 与 stop。断言：

- 原始文件最后交易日等于 committed `market_date`；
- response 日期等于该 `market_date`；
- candidate 字段与 scanner row 完全一致；
- 不读取历史 trade/candidate artifact。

若 exact next eligible open 不在 committed epoch 中，结论只能是 `PENDING_NEXT_OPEN` / `NO_FRESH_EXCHANGE_QUOTE`，不得回填、倒推、补单或称为价格拒绝。即使原始 setup 成立，只要 frozen replay/release gate 未通过，必须保持 research-only，不能生成 BUY。