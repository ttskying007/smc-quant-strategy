# V41 Replay Entry/Exit Review — 持仓上限安全微调

日期: 2026-05-23

## 背景
用户明确校正后续迭代顺序：

1. 第一先判断选股/信号是否正确：信号后 30/60 天是否真的有趋势空间。
2. 第二判断入场是否正确：是否买早、是否入场后先大幅回撤、是否未到入场点位。
3. 第三判断出场是否正确：是否刚卖出不久就涨、是否持股太短没吃到趋势、是否超过 30 天仍不涨。

这不是单纯优化 WR/RR，而是交易级 replay autopsy。聚合指标只能作为验证结果，不能替代逐笔复盘。

## V40 后继续复盘结论
V40 已修复 V39 的主要卖早问题，但仍发现：

- 部分 breakeven / trailing 出场后继续涨。
- 剩余问题交易集中在：
  - `000636.SZ`: SL 后又涨，属于入场/止损位置仍不理想。
  - `001872.SZ`, `600585.SH`, `603639.SH`: 低收益或 breakeven 出场后仍有后续空间。
- 激进长持仓/取消保护虽然总收益高，但会明显降低胜率并提高 SL 率。

## 测试过但拒绝的激进方向
候选：

- 不做 breakeven。
- 不做 trailing。
- 120/150 bar 长持仓。
- 0%/10%/20% 小比例止盈。
- 长趋势完全放开。

代表结果：

| 方案 | WR | SL率 | Avg PnL | Total PnL |
|---|---:|---:|---:|---:|
| 激进长持仓 | 76.9% | 23.1% | +11.11% | +144.40% |
| V40 | 92.3% | 7.7% | +4.44% | +57.67% |

拒绝原因：收益更高但质量门槛失败，WR 降至 76.9%、SL 率升至 23.1%。这类方案不能上线为正式版本，只能作为研究候选。

## V41 安全改动
正式采用的唯一安全改动：

```text
max_hold_bars: 75 → 120
```

保持 V40 其它规则不变：

```text
TP1 = 1.5R，卖 30%
TP2 = 3.2R，卖 25%
剩余 45% trend runner
breakeven 规则不放松
trailing 仍然 6R 后触发
```

原因：V40 中有一类信号不是错，而是发力慢；延长持仓上限能吸收慢趋势，同时不增加 SL 率。

## V40 → V41 指标

| 版本 | 交易数 | WR | SL率 | Avg PnL | Total PnL |
|---|---:|---:|---:|---:|---:|
| V40 | 13 | 92.3% | 7.7% | +4.44% | +57.67% |
| V41 | 13 | 92.3% | 7.7% | +4.51% | +58.66% |

改动收益：

```text
交易数不变
WR 不变
SL率不变
Avg PnL +0.07pp
Total PnL +0.99pp
```

## 文件

```text
/root/.hermes/scripts/v25/v41_final_engine.py
/root/.hermes/smc_opt_v41/v41_trades.json
/root/.hermes/smc_opt_v41/v41_picks.json
/root/.hermes/smc_opt_v41/v41_setups.json
/root/.hermes/smc_opt_v41/v41_metrics.json
/root/.hermes/smc_opt_v41/v41_replay_entry_exit_report.json

/root/.hermes/smc_opt_v41p/v41_targeted_exit_grid.json
/root/.hermes/smc_opt_v41p/v41_targeted_best_trades.json
```

## Future iteration rule
下一步不要继续只放宽出场。真正需要针对：

- 信号后确实涨，但先打 SL / 先大回撤的案例。
- 首次确认入场 vs 二次回踩入场。
- 50% 首次确认 + 50% 二次确认。
- entry_price 是否应更贴近 zone_high / zone_mid。
- SL 是否应放在 liquidity low，而不是固定 zone_low buffer。

所有后续版本必须继续遵守三段复盘顺序：

```text
信号存在且正确？ → 入场点正确？ → 出场是否卖早/没吃趋势？
```
