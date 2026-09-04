# V294 entry-session second/third 60m persistence audit

## 触发场景

V293 已证明：在 V292 `first60_bull_hold_zone` 659 笔基线上，买点前已知的 entry-session first60 市场/行业同步扩散是强增益层：`M_UP>=65 & I_UP>=65` 得到 172 笔 / WR 70.35 / Avg +2.62 / 2025 WR 77.11 / 2026 WR 64.04，但月度最低仍 33.33。V294 继续验证：first60 同步上涨到底是开盘集体脉冲，还是能持续到第二/第三个 60m bar 的真实接管。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v294_entry60_persistence_audit.py`
- 结果：`/root/.hermes/smc_audit/v294_entry60_persistence_latest.json`
- 输入：V293 enriched rows / V292 `first60_bull_hold_zone` 659 笔。
- 数据：本地 60m cache 4553 只 + Baostock industry map。
- 执行模拟：只在第 2 或第 3 根 60m 收盘时，若个股仍 hold zone、市场/行业上涨占比持续达标，则以该 60m close 入场；SL=`zone_low*0.992`，日线 T+1 replay。
- 防未来函数：第 k 根 60m close 入场只使用 k 根以内的当日 60m 信息；退出从下一交易日开始。
- 写入：no-write；不写 production/frontend/watchlist。

## 基线

| 来源 | N | WR | Avg | SL% | GAP_SL% | 2025 | 2026 | 月度最低 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V292/V293 source | 659 | 56.60 | +1.09 | 38.39 | 2.73 | 62.21 | 53.85 | 38.36 |
| V293 first60 `M_UP>=65 & I_UP>=65` | 172 | 70.35 | +2.62 | 24.42 | 2.33 | 77.11 | 64.04 | 33.33 |

## V294 结果

最佳可执行延迟入场：

| 条件 | N | WR | Avg | SL% | GAP_SL% | 2025 | 2026 | 月度最低 | T+1违规 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `k=2, market_up>=65, industry_up>=50, stock hold zone` | 181 | 71.27 | +2.85 | 21.55 | 1.66 | 74.44 | 68.13 | 45.00 | 0 |

Top variants:

| Variant | N | WR | Avg | 2025 | 2026 | 月度最低 |
|---|---:|---:|---:|---:|---:|---:|
| k2_mup65_iup50_raw | 181 | 71.27 | +2.85 | 74.44 | 68.13 | 45.00 |
| k2_mup65_iup50_nodecay | 169 | 70.41 | +2.71 | 74.16 | 66.25 | 40.00 |
| k2_mup65_iup65_raw | 156 | 70.51 | +2.84 | 74.12 | 66.20 | 40.00 |
| k2_mup50_iup50_nodecay | 246 | 65.85 | +2.14 | 71.82 | 61.03 | 43.48 |
| k3_mup50_iup65_nodecay | 190 | 65.79 | +2.37 | 76.09 | 56.12 | 37.50 |

## 月度复盘

最佳 k2 规则月度：

| 月份 | N | WR | Avg | 出口结构 |
|---|---:|---:|---:|---|
| 202511 | 9 | 55.56 | +2.53 | SL2 / TP4 / TIME3 |
| 202512 | 81 | 76.54 | +3.57 | TP48 / SL10 / GAP_SL2 / TIME21 |
| 202601 | 34 | 94.12 | +5.06 | TP32 / SL1 / TIME1 |
| 202602 | 11 | 45.45 | -0.51 | TP4 / SL5 / GAP_SL1 / TIME1 |
| 202603 | 20 | 45.00 | -0.80 | TP9 / SL11 |
| 202604 | 16 | 50.00 | +0.78 | TP7 / SL8 / TIME1 |
| 202605 | 10 | 80.00 | +4.01 | TP8 / SL2 |

关键弱点：V294 把年度和整体质量显著抬升，但 202602-202604 仍弱，说明 second60 persistence 解决了“开盘脉冲假象”的一部分，却仍无法识别 2026 春季局部 regime 的行业退潮/结构失败。

## 机制结论

1. **方向有效**：从 first60 同步扩散升级到 second60 可执行持续性，WR 70.35→71.27，Avg 2.62→2.85，GAP_SL 2.33→1.66，2026 WR 64.04→68.13，月度最低 33.33→45.00。
2. **最佳不是更强行业阈值，而是市场强 + 行业不弱**：`market_up>=65 & industry_up>=50` 优于过严 `industry_up>=65`，说明行业只要跟随即可，过严会牺牲样本而不显著提升稳定性。
3. **第三根 60m 不优于第二根**：k3 变体 WR 和月度稳定性下降，说明等待过久会追价/错过接管初段。
4. **仍不能生产**：n=181，月度最低 45，距离生产稳定性仍不足；只可作为下一轮研究基线。
5. **下一步方向**：针对 202602-202604 弱月做 regime/loss root-cause。重点验证：是否由市场/行业日内扩散反转、行业退潮、个股 second60 追价过高、risk_after_persist 偏高、或 SL 仍锚点过窄导致。

## 验证

Focused ad-hoc verification PASS：

```json
{
  "status": "PASS",
  "checked": [
    "bucket helpers",
    "metrics aggregation",
    "artifact/no-write/T+1/best-row contract"
  ],
  "best_n": 181,
  "best_wr": 71.2707,
  "best_avg": 2.8456,
  "t1_violations": 0
}
```

这是专项验证，不是完整 canonical test suite green。
