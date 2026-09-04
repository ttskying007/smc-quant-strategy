# V295 V294 weak-month root-cause audit

## 触发场景

V294 已把 V292/V293 的 `first60_bull_hold_zone` 基线推进到可执行 second60 persistence：`k=2, market_up>=65, industry_up>=50, stock hold zone`，181笔 / WR 71.27 / Avg +2.85 / 2025 WR 74.44 / 2026 WR 68.13 / GAP_SL 1.66 / T+1=0。问题只剩 202602-202604 弱月：45.45 / 45.00 / 50.00。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v295_v294_weak_month_root_cause.py`
- 结果：`/root/.hermes/smc_audit/v295_v294_weak_month_root_cause_latest.json`
- 输入：V294 best rows `v294_best_rows.csv`，181笔。
- 写入：no-write；不写 production/frontend/watchlist。
- 防未来函数：只分析 V294 已在 entry-session 第2根60m收盘时可得字段，不使用后验 MFE/MAE 或未来日线结果作为 selector。

## 核心结果

| 分组 | N | WR | Avg | TP% | SL% | GAP_SL% | 月度 |
|---|---:|---:|---:|---:|---:|---:|---|
| V294 baseline | 181 | 71.27 | +2.85 | 61.88 | 21.55 | 1.66 | min 45.00 |
| 强月(非202602-04) | 134 | 79.85 | +3.91 | 68.66 | 11.19 | 1.49 | min 55.56 |
| 弱月(202602-04) | 47 | 46.81 | -0.19 | 42.55 | 51.06 | 2.13 | 45.45/45.00/50.00 |

弱月不是微利污染，而是 **SL主导**：SL 51.06%，强月仅 11.19%。

## 机制差异

| 字段 | 弱月中位 | 强月中位 | 解释 |
|---|---:|---:|---|
| risk_after_persist | 6.10 | 5.46 | second60 入场后离 SL 更远，风险变大 |
| open_to_confirm_pct | 1.37 | 1.37 | 整体追价中位差异不大，但弱月亏损中位 1.79 |
| stock60_volx | 1.29 | 1.04 | 弱月放量更强但失败，像出货/冲高回落 |
| acc_range_pct | 7.74 | 5.83 | 弱月前置蓄势区更宽，结构更松散 |
| post_hold_min_pct | 3.38 | 2.76 | second60 hold 后仍有更大下探，说明接管不稳 |
| persist_mkt_up | 78.93 | 81.95 | 弱月市场扩散略弱 |
| persist_mkt_decay | 3.23 | 5.44 | 弱月市场扩散持续性更差 |

## 弱月亏损集中点

| 维度 | 表现 |
|---|---|
| lifecycle | `ACC_WIDE>=7|SWP_SHALLOW<1|IMP_WEAK<0.5`：10笔 / WR30 / Avg -2.84 / SL70 |
| lifecycle | `ACC_MID4_7|SWP_SHALLOW<1|IMP_MID0.5_1.5`：5笔 / WR0 / SL100 |
| sweep | `SWP_SHALLOW<1`：30笔 / WR36.67 / Avg -1.72 / SL63.33 |
| industry | `C26 化学原料和化学制品制造业`：10笔 / WR30 / SL70 |
| industry | `C39 计算机、通信和其他电子设备制造业`：8笔 / WR25 / Avg -5.46 / SL62.5 |

## Entry-time rule 探索

只用 entry-time 可得字段搜索，最佳候选：

| Rule | N | WR | Avg | 2025 | 2026 | 月度WR |
|---|---:|---:|---:|---:|---:|---|
| `open_to_confirm_pct<=1.5 & stock60_pos>=50` | 81 | 80.25 | +3.40 | 81.82 | 78.38 | 202602 60 / 202603 62.5 / 202604 60 |
| `persist_stock_ret<=1.5 & post_hold_min_pct<=4` | 88 | 78.41 | +3.32 | - | 83.72 | 弱月 60/66.67/66.67 |
| `gap_from_zone>=2 & stock60_pos>=50` | 119 | 75.63 | +3.69 | - | 71.15 | 弱月 66.67/57.14/55.56 |

注意：这些规则样本仍小，部分月份 min_n 过低，只能作为下一轮 V296 的待验证 anti-chase / lifecycle gate，不可生产。

## 结论

1. V294 弱月根因不是 T+1、不是微利伪胜率、不是简单行业阈值不够强，而是 **second60 persistence 在 202602-202604 遇到“浅扫 + 宽蓄势 + 弱/中等impulse + 放量但接管不稳”的假接管结构**。
2. 弱月 SL 从强月 11.19% 跳到 51.06%，说明问题在入场前结构质量，而不是退出参数。
3. 有效修复方向不是继续加市场/行业 up 阈值，而是：
   - anti-chase：限制 `open_to_confirm_pct` / `persist_stock_ret`；
   - persistence risk：限制 `risk_after_persist` / `post_hold_min_pct`；
   - lifecycle gate：排除 `SWP_SHALLOW<1 + IMP_WEAK/MID + ACC_MID/WIDE` 的假接管；
   - 行业弱期只作辅助诊断，不直接生产删除行业。
4. 下一步 V296 应在 V293/V294 全 659 行上重新模拟：`second60 persistence + anti-chase + lifecycle gate`，而不是只在 V294 181 行上后验过滤。

## 验证

Focused ad-hoc verification PASS：脚本 import、helper、真实 artifact/no-write、T+1、source row count、summary metrics 均通过。该验证不是完整 canonical test suite green。
