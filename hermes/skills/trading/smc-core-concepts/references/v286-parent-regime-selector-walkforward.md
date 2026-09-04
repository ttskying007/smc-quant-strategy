# V286 父级市场/行业 Regime 选择器 Walk-forward 审计

## 触发场景

V285 证明每股历史 DNA 不能稳定外推：2025 有改善，但 2026 明显失效。下一步验证用户提出的“自适应”是否应从每股 DNA 上移到父级状态：用 entry 前一交易日可得的市场/行业参与度，选择当天允许的时间顺序语法族/规则。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v286_parent_regime_selector_walkforward.py`
- 摘要：`/root/.hermes/smc_audit/v286_parent_regime_selector_latest.json`
- 产物：`/root/.hermes/smc_audit/v286_parent_regime_selector_no_write_20260703_153509/`
- 输入：V280 全量 82,400 日线时间顺序候选；V282 同源前一交易日市场/行业参与度。
- 防未来函数：训练只用测试年前的年份；市场/行业特征只用 entry 前一交易日。
- 生产/前端/watchlist 写入：全部 false。
- T+1：验证 0 违规。

## Walk-forward 结果

基线 2024-2026：70,556 笔，WR 47.33%，Avg +0.68%，2026 WR 40.17%。

| Selector | N | WR | Avg | 2024 | 2025 | 2026 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| loose_state_n20_wr52_avg0 | 4,482 | 47.90% | +0.84% | 46.86 | 53.27 | 36.93 | 2026 更差 |
| balanced_state_n50_wr54_avg05 | 5,323 | 50.89% | +1.37% | 53.56 | 52.08 | 36.97 | 2024/25 提升，2026 崩 |
| strict_state_n100_wr56_avg1 | 2,801 | 47.13% | +0.88% | 49.46 | 49.93 | 38.20 | 不稳定 |
| broad_state_n100_wr52_avg05 | 5,511 | 43.82% | +0.44% | 44.07 | 49.47 | 35.71 | 明显失败 |

## 诊断发现

非 walk-forward 的诊断面能找到小样本强口袋，例如：

| 口袋 | N | WR | Avg | 年度 WR |
|---|---:|---:|---:|---|
| MRET>=1/MUP>=65 + UP_CONT_BOS_OB/DOWN/LIQ>20/RISK>=8 | 104 | 69.23% | +3.33% | 2024 67.47 / 2025 76.92 / 2026 75.00 |
| MUP>=65/IUP>=65 + RANGE_SWEEP/RANGE/LOW_VOL/RISK>=8 | 109 | 71.56% | +4.25% | 2024 75.00 / 2025 66.67 / 2026 70.83 |
| MRET>=1/IRET>=1 + UP_CONT_BOS_OB/DOWN/RISK>=8 | 115 | 71.30% | +3.50% | 2024 70.79 / 2025 81.82 / 2026 66.67 |

但这些是全测试期诊断，不是生产验证；年度样本尤其 2026 只有个位/十几笔，不能直接晋级。

## 结论

1. 父级市场/行业参与度确实能解释一部分高质量口袋。
2. 但按历史年份自动选择状态+语法规则，在 2026 仍然失败，说明“用去年最优父级状态规则”不能直接生产。
3. 2026 的退化不是单股 DNA 问题，也不是简单父级 regime 白名单能解决的问题；它更像 execution/entry 结构与当日资金接管质量问题。
4. 下一步不能继续堆历史 fit 选择器；必须转向 same-source lower timeframe generator：先在 60m 生成 sweep/reclaim/MSS/HL POI，再映射到日线执行，而不是用日线 POI 反查 60m。

## 使用注意

- V286 是 no-write 研究，不得接生产。
- 非 walk-forward 小口袋可作为方向线索，不可作为生产指标。
- 任何父级 regime 选择器若要生产，必须有 forward/monthly 稳定性和足够每年样本，而不是只看整体 WR。