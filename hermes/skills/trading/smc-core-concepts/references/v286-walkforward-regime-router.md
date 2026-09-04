# V286 走步父级 Regime Router 审计教训

## 触发场景

V285 证明“每股历史 DNA → 未来选择时间顺序组合”不能稳定外推；V282 证明前日市场/行业参与度能提高质量但仍是 in-sample 诊断。V286 继续验证：能否用 **只来自 prior years 的全局父级 regime router**，在下一年选择该交易的时间顺序语法面。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v286_walkforward_regime_router_audit.py`
- 最新摘要：`/root/.hermes/smc_audit/v286_walkforward_regime_router_latest.json`
- 产物目录：`/root/.hermes/smc_audit/v286_walkforward_regime_router_no_write_20260703_092402/`
- 输入：V280 全量 82,400 个分层日线时间顺序事件。
- 状态字段：entry 前一交易日全市场/行业涨跌中位数、上涨占比、行业相对市场强弱；事件发生时的 family/regime/risk/liq/range/volume/displacement。
- 训练方式：2024 用 2023 训练；2025 用 2023-2024；2026 用 2023-2025。
- 防未来函数：只使用测试年前历史结果选择规则；市场/行业状态只用 entry_date 前一交易日。
- 写入：`no_write=true`，`production_write=false`，`frontend_write=false`，`watchlist_write=false`。
- T+1：验证 `t1_violations=0`。

## 基线

| 范围 | n | WR | Avg | SL% | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V280 2024-2026 全测试期 | 70,556 | 47.33% | +0.68% | 40.47% | 46.00 | 51.31 | 40.17 |

## 走步 Router 结果

| Router | n | WR | Avg | SL% | 2024 | 2025 | 2026 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| broad_prior_regime | 4,921 | 53.97% | +1.97% | 30.05% | 56.84 | 48.85 | 46.12 | 大幅降 SL，但未达生产 |
| balanced_prior_regime | 4,006 | 55.82% | +2.31% | 27.23% | 57.92 | 51.43 | 45.16 | 更强但 2026 仍弱 |
| strict_prior_regime | 1,562 | 56.34% | +2.81% | 22.98% | 56.91 | 55.60 | 49.35 | 年度更稳，但量下降 |
| quality_prior_regime | 1,255 | 60.80% | +3.63% | 19.12% | 60.22 | 69.52 | 55.93 | 当前最佳研究候选，仍低频 |

## 关键发现

1. **父级 regime router 明显有效**：相比 V280 测试基线 47.33% WR / 40.47% SL，quality router 达到 60.80% WR / 19.12% SL，说明“先判断市场/行业/语法适用状态，再选时序组合”方向正确。
2. **这比每股 DNA 更可靠**：V285 stock DNA 2026 约 40% WR；V286 quality router 2026 为 55.93%，说明问题更像年度/市场 regime，而不是股票固定性格。
3. **仍不能直接生产**：quality router 2026 只有 59 笔，三年测试总 1,255 笔，覆盖不足；60.8% WR 低于 Lei 对生产级 SMC 的预期。
4. **当前最佳稳定形态**：`RANGE_LOW_SWEEP_RECLAIM | RANGE | RISK>=8 | 前日市场RET>=1 | 前日行业RET>=1` 及其更细分版本在 prior-year 和 test-year 都反复出现，是后续同源多周期生成器的优先父级状态。
5. **in-sample 诊断提示另一个候选**：`UP_CONT_BOS_OB | DOWN | RISK>=8 | M_RET>=1 | I_RET>=1` 在 2024-2026 测试期 n=115 / WR=71.30 / Avg=+3.50 / 年度 WR 70.79/81.82/66.67，但 walk-forward 选择样本仍小；下一步需要扩大/重建同源候选，不是直接上线。

## 结论

V286 第一次把“时间顺序组合 + 自适应状态”从 in-sample 诊断推进到 prior-year walk-forward：方向有效，但仍不是最终生产闭环。

下一步不要再做 per-stock DNA 白名单；应做 **V287 same-source regime generator**：以 V286 发现的强父级状态为入口，从 60min/日线同源生成 POI（先 60min sweep/reclaim/MSS/HL，再映射日线 regime），验证是否能在保持 2026 稳定的同时扩大 n。

## 使用注意

- V286 是研究审计，不得接生产或前端。
- 任何后续 production 迁移必须先通过 dry-run scanner contract：规则字段必须可在实时 scanner 决策时获得，不能依赖 pnl/reason/post-entry 字段。
- 同日市场/行业收盘广度仍只能诊断，不能生产；生产候选只能用 entry 前一交易日或更早状态。
