# V246/V334 当前供给与全宇宙闭环审计教训

## 触发场景

当历史 selected-only 结果看起来达到生产门槛（例如 V246 约 573 笔、WR 94%+、avg 7.6%+），但当前扫描/前端供给不足或用户要求继续深挖时，不能直接把历史 selected rows 晋级生产。必须先证明同一规则能在当前扫描器、全候选宇宙、T+1 执行重放下同时成立。

## 强制审计顺序

1. **分离历史 selected quality 与当前可复现供给**
   - 历史 selected rows 只能证明“过去被选中的集合质量高”。
   - 必须按 source lineage 拆分：例如 V161/V164、V175、V211 child、旧 strict parent。
   - 审计当前 strict parent 是否真的能重构历史 selected population；若覆盖率极低（本轮仅约 3.7%），说明当前规则不是历史高质量路线的真实生成器。

2. **重建当前谱系供给**
   - 从 scanner dry-run / current candidate stream 重新生成候选。
   - 重新计算 market breadth、industry participation、all-market strong1 等前置字段。
   - 检查 stale cache：breadth/market environment 缓存停在旧日期会误杀当前供给。修复方式是从 kline cache 全量重建 cache，而不是放宽交易规则。

3. **T+1 可执行重放当前候选**
   - 对当前 non-history actionable rows 逐笔 replay。
   - 退出规则至少包含：`SL = zone_low * 0.99`、`TP = entry + 1.5R`、`max_hold = 10 bars`、只允许 entry date 之后的 bar 出场。
   - 已 TP/SL/TIME 的行不能当作当前 OPEN 候选推给前端。

4. **selected-only 切片必须回到全宇宙验证**
   - 如果在 historical selected rows 中找到高质量 slice（如 bull_count_3、strong1、zone width），下一步必须把同一谓词应用到完整 dry-run universe。
   - 若回到 full universe 后 WR/avg/年度稳定性掉到门槛以下，结论是 selected-only 污染，不可晋级。

5. **数值阈值前沿搜索用于关闭“只是参数没调好”的疑问**
   - 对 pre-entry numeric fields 做 quantile threshold search：risk、chase、zone width、reclaim body/position、pullback depth、breadth、industry participation 等。
   - 搜索 singles/pairs/triples 时必须禁止 outcome 字段。
   - 若高 WR 规则样本小、avg 低、current supply 为 0，而大样本规则 WR/avg 不达标，即可判定该信号族存在 full-universe ceiling。

## 本轮可复用结论

- V246 历史 selected quality 真实，但不能单独作为生产依据。
- stale breadth cache 修复后，当前供给会恢复；但供给恢复不等于信号族可晋级。
- V330 这类 current-open quality slice 在 selected-only 集合里可能很漂亮；必须用 V331 类 full-universe validation 排除假晋级。
- V333/V334 证明：V164/V246 族不是简单门禁粗糙问题，而是 full-universe 上限不足。大样本通常卡在约 90%–92% WR，达不到生产门槛；高 WR 子集样本不足或当前无供给。

## 晋级/关闭判定模板

生产晋级至少同时满足：

| 维度 | 最低要求 |
|---|---:|
| 历史 closed n | >= 570 |
| 最小年度 n | >= 70 |
| 总 WR | >= 93% |
| 平均收益 | >= 7.6% |
| 最低年度 WR | >= 91% |
| 微利污染 | <= 1% |
| T+1 违规 | 0 |
| 当前 non-history OPEN/actionable | >= 1 |

若 full-universe 搜索和 numeric frontier 都无通过规则，应明确关闭该信号族晋级路线，转向新的供给层/信号发生器，不再继续围绕同一族微调阈值。

## 工具实现注意

- 审计脚本优先输出 JSON + CSV。不要依赖 parquet，运行环境可能没有 pyarrow/fastparquet；CSV 更稳。
- 任何缓存修复必须标注 no-write 范围：可写 audit cache/report，但不得写 production/frontend/watchlist。
- 报告要区分：历史 selected pass、current supply pass、T+1 executable pass、full-universe pass、numeric frontier pass。不要把其中一个 pass 当作整体完成。
