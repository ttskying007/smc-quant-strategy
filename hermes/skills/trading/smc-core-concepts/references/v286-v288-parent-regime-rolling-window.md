# V286-V288 父级 Regime + 滚动窗口审计闭环

## 触发场景

用户要求继续深入研究“按时间顺序发生的指标组合、参数不固定、大小周期、个股 DNA 自适应”的方向。V280-V285 已证明：

- SMC 原始/分层时序机会并不少，V280 全量 82,400 笔。
- 固定时间顺序参数质量不够。
- 每股历史 DNA walk-forward 失效，2026 明显退化。
- 前日市场/行业参与度有效但不足。

本轮继续验证真正瓶颈是否是：缺少父级市场/行业 regime，以及前日状态过短视，是否需要 3/5/10/20 日滚动参与度窗口。

## V286：父级市场/行业 Regime Walk-forward

- 脚本：`/root/.hermes/scripts/v25/v286_parent_regime_walkforward_audit.py`
- 摘要：`/root/.hermes/smc_audit/v286_parent_regime_walkforward_latest.json`
- 输入：V280 82,400 笔 + entry 前一交易日市场/行业参与度。
- 写入：no-write，未写 production/frontend/watchlist。

### 结果

| Selector | N | WR | Avg | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|
| loose_parent | 13,930 | 54.08% | +2.18% | 56.10 | 52.78 | 44.09 |
| balanced_parent | 11,224 | 51.90% | +1.57% | 54.63 | 53.22 | 44.11 |
| strict_parent | 8,287 | 53.28% | +1.58% | 58.88 | 53.01 | 44.98 |
| stability_parent | 14,239 | 53.90% | +2.14% | 56.11 | 52.78 | 44.79 |

结论：父级 selector 能显著提高总体质量和交易量，但 2026 仍卡在约 44%-45%，说明“前一日市场/行业强度 + broad rule selection”仍不足以生产。

### V286 发现的关键口袋

`UP_CONT_BOS_OB | DOWN | 前日市场涨幅>=1 | 前日行业涨幅>=1 | risk>=8`

测试期：N=115，WR=71.30%，Avg=+3.50%，2026 WR=66.67%。

这个口袋说明正确方向不是吸收反转，而是：

> 大盘/行业已经同步接管后，在个股仍处 DOWN regime 时出现 UP_CONT_BOS_OB 的趋势接管延续。

## V287：强参与度 UP_CONT 口袋复盘

- 脚本：`/root/.hermes/scripts/v25/v287_strong_participation_upcont_pocket_audit.py`
- 摘要：`/root/.hermes/smc_audit/v287_strong_participation_upcont_pocket_latest.json`

### 关键结果

| Rule | N | WR | Avg | 2024 | 2025 | 2026 | SL% |
|---|---:|---:|---:|---:|---:|---:|---:|
| UP_CONT + DOWN + 强市场/行业 + risk>=8 | 115 | 71.30% | +3.50% | 70.79 | 81.82 | 66.67 | 13.04 |
| + EUPHORIA breadth | 114 | 71.05% | +3.40 | 70.79 | 81.82 | 64.29 | 13.16 |
| + rel industry 0-10 | 82 | 69.51% | +3.07 | 68.75 | 85.71 | 63.64 | 13.41 |
| + range>=25 | 107 | 70.09% | +3.19 | 70.93 | 75.00 | 61.54 | 14.02 |
| highvol broad | 196 | 59.69% | +2.16 | 57.48 | 70.00 | 55.17 | 30.10 |
| no risk8 broad | 303 | 60.40% | +1.98 | 60.53 | 63.77 | 54.55 | 28.05 |

结论：risk>=8 是核心质量门槛，能把 SL 从约 28%-30% 压到 13%左右，但交易量下降到 115 笔。高波动/宽松版本增加交易量但月度坏段明显。

## V288：3/5/10/20 日滚动市场/行业窗口

- 脚本：`/root/.hermes/scripts/v25/v288_rolling_regime_window_audit.py`
- 摘要：`/root/.hermes/smc_audit/v288_rolling_regime_window_latest.json`

### 关键结果

| Rule | N | WR | Avg | 2024 | 2025 | 2026 | SL% | 说明 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| UP_CONT DOWN risk8 + W10_RET_POS | 190 | 80.53% | +4.76 | 84.09 | 73.17 | 70.59 | 7.89 | 当前最佳均衡口袋 |
| UP_CONT DOWN + W10_RET_POS | 626 | 63.58% | +2.19 | 66.79 | 60.91 | 61.32 | 26.52 | 放大量版本，跨年稳定 |
| UP_CONT DOWN + W5_RET_POS | 523 | 59.08% | +1.65 | 60.16 | 58.06 | 58.14 | 28.68 | 更高频但质量下降 |
| UP_CONT DOWN risk8 + W5_STRONG1_25 | 273 | 71.06% | +3.61 | 72.83 | 74.19 | 57.89 | 15.38 | 交易量较好但 2026 降低 |
| UP_CONT DOWN + W5_UP60 | 246 | 70.73% | +2.77 | 73.40 | 63.33 | 60.71 | 19.11 | 中等口袋 |

### 关键结论

1. **前一日强度太短视**：V287 虽然 71% WR，但 N=115。滚动窗口能解释坏月段并扩展样本。
2. **10 日市场/行业正参与是最强父级窗口**：`W10_RET_POS` 把 UP_CONT_DOWN_RISK8 扩展到 N=190、WR=80.53%、2026 WR=70.59%、SL=7.89%。
3. **放宽 risk8 后仍可稳定**：`UP_CONT_DOWN + W10_RET_POS` 达 N=626、WR=63.58%，2024/2025/2026 全部 >60%。这是目前第一个“交易量较大 + 跨年不崩”的方向。
4. **这不是单股 DNA，而是板块/市场接管窗口**：高质量来自 market+industry rolling regime，而不是个股历史白名单。
5. **仍未接生产**：V288 是研究审计，尚未证明可从当前 scanner 合约实时生成，也未做逐笔信号视觉审计。

## 下一步

若继续推进生产候选，优先验证：

1. 对 `UP_CONT_DOWN + W10_RET_POS` 和 `risk8` 版本做逐笔审计：确认 BOS/OB/entry 不存在未来函数、T+1 无违规。
2. 建立 dry-run scanner contract：证明 W10 市场/行业参与度、UP_CONT_BOS_OB、DOWN regime、risk 可以在 scanner-time 从原始 K 线实时计算。
3. 对 2026 逐笔复盘剩余亏损，判断是否由 gap、行业分化、个股高位、或 OB 语义错误导致。
4. 在未完成 dry-run 合约前，不得写 production/frontend/watchlist。
