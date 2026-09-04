# V293 entry-session 60m participation + lifecycle overlay

## 触发场景

V292 已证明：同源 60m-first 信号下，次日 60m hold/continuation 入场比开盘追入更合理，但 best `first60_bull_hold_zone` 仍只有 659 笔 / WR 56.60 / Avg +1.09 / 2026 WR 53.85 / 月度最低 38.36。V293 继续验证：若没有 15m、盘口、竞价数据，是否能用 **买入前已知的 entry-session first60 市场/行业同步扩散 + pre-entry lifecycle** 区分真实接管与假持续。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v293_entry60_participation_lifecycle_audit.py`
- 结果：`/root/.hermes/smc_audit/v293_entry60_participation_lifecycle_latest.json`
- 输入：V292 best rows `first60_bull_hold_zone`，659 笔。
- 数据：60m cache 约 4553 只；entry day 第一根 60m K线的全市场/行业同步涨幅、上涨占比、成交量 proxy。
- 防未来函数：因为 V292 买点是 first60 close，entry60 全市场/行业 first60 状态在买点时已知；不使用当天后续 K线、退出结果选股。
- 写入：no-write；不写 production/frontend/watchlist。
- T+1：验证 `t1_violations=0`。

## 基线

| 来源 | N | WR | Avg | SL% | GAP_SL% | 2025 | 2026 | 月度最低 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V292 first60_bull_hold_zone | 659 | 56.60 | +1.09 | 38.39 | 2.73 | 62.21 | 53.85 | 38.36 |

## V293 结果

最佳大样本表面：

| 条件 | N | WR | Avg | SL% | GAP_SL% | 2025 | 2026 | 月度最低 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| entry60 `M_UP>=65 & I_UP>=65` | 172 | 70.35 | +2.62 | 24.42 | 2.33 | 77.11 | 64.04 | 33.33 |

其他有信息但样本偏小：

| 条件 | N | WR | Avg | 2025 | 2026 | 备注 |
|---|---:|---:|---:|---:|---:|---|
| `M_UP>=65 & I_UP50_65` | 39 | 74.36 | +2.63 | 69.23 | 76.92 | 样本小 |
| `CONF1_2 & I_RET_0_1` | 113 | 69.03 | +2.31 | 77.27 | 63.77 | 说明 first60 不能过强追高 |
| lifecycle `ACC_TIGHT<4|SWP_SHALLOW<1|IMP_WEAK<0.5` | 52 | 65.38 | +1.64 | 64.71 | 65.71 | lifecycle proxy 有信息但低频 |

## 机制结论

1. **entry-session first60 市场/行业同步扩散是目前最强增益层**：从 V292 56.60% WR 提升到 70.35%，SL 从 38.39% 降到 24.42%。
2. **信号含义变清楚**：不是“个股 first60 阳线”本身有效，而是“个股 hold + 同小时全市场/行业 65%+ 同步上涨”才像真实接管。
3. **仍不能生产**：n=172，月度最低 WR 33.33，说明仍受月份 regime 冲击；不能用它直接替换生产选股。
4. **下一步方向明确**：需要 15m/竞价/成交额持续性或更细粒度行业扩散，验证 first60 同步上涨是否只是第一小时集体脉冲，还是能持续到第二/第三小时。

## 后续方向

V294 应继续在 no-write 下测试：

`V292 first60 hold → entry60 market/industry >=65% → first2/first3 60m continuation breadth persistence → stock does not lose first60 low/zone → T+1 daily exit`

如果 first60 同步强但 second60/third60 扩散不持续，则月度低谷可能来自开盘集体脉冲后的行业退潮。

## 验证

Focused ad-hoc verification PASS：
- helper bucket boundaries；
- metrics aggregation；
- enriched row artifact + T+1/no-write invariants；
- headline overlay improvement guard。

这是专项验证，不是完整 canonical test suite green。