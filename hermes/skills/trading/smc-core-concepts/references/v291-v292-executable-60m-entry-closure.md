# V291-V292 可执行 60m 入场闭环（no-write）

## 背景

V288 用同源 60m 生成 `SSL sweep → reclaim → micro MSS → 60m POI → 次日开盘买入`，全市场可用 60m 缓存上得到：1434 笔，WR 52.86%，Avg +0.51%，2025/2026 都约 53%，但仍远低生产。

V289/V290 证明 participation / lifecycle proxy 有信息，但样本小或月度不稳。下一步验证执行方向：同一 60m 信号下，是等次日回踩 60m POI 更好，还是等次日 60m 继续确认更好。

## V291：次日 POI limit 回踩入场失败

脚本：`/root/.hermes/scripts/v25/v291_intraday_limit_entry_audit.py`
结果：`/root/.hermes/smc_audit/v291_intraday_limit_entry_latest.json`

设计：保持 V288 信号不变，次日预挂买入 limit 到同源 60m POI：`zone_high / zone_618 / zone_mid / zone_382 / zone_low`，只用 entry day 60m 是否触及判断成交，退出仍严格 T+1。

关键结果：

| 入场模式 | N | Fill | WR | Avg | 2025 | 2026 | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| daily open baseline | 1434 | 100% | 52.86 | +0.51 | 52.63 | 52.95 | 0 |
| zone_high first2 60m | 462 | 32.22% | 40.48 | -0.57 | 40.20 | 40.56 | 0 |
| zone_618 all session | 381 | 26.57% | 40.16 | -0.60 | 38.64 | 40.61 | 0 |
| zone_mid all session | 361 | 25.17% | 38.50 | -0.67 | 35.37 | 39.43 | 0 |
| zone_low first2 60m | 219 | 15.27% | 34.25 | -0.82 | 25.00 | 37.13 | 0 |

结论：**次日回踩原 60m POI 是毒性选择，不是更优入场。** 一旦信号成立后次日又打回 POI，更多代表接管失败/zone 再次受压，而不是“便宜买点”。不要把 V288 60m-first 信号改成次日 limit 回踩入场。

## V292：次日 60m 继续确认有弱正增益，但仍不达生产

脚本：`/root/.hermes/scripts/v25/v292_next_session_60m_confirmation_audit.py`
结果：`/root/.hermes/smc_audit/v292_next_session_60m_confirmation_latest.json`

设计：保持 V288 信号不变，次日不追 open，也不等回踩；等待 entry day 第一个/前几个 60m 出现继续确认后才买，退出仍严格 T+1。

关键结果：

| 入场模式 | N | Fill | WR | Avg | 2025 | 2026 | GAP_SL | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| first60_bull_hold_zone | 659 | 45.96% | 56.60 | +1.09 | 62.21 | 53.85 | 2.73% | 0 |
| first60_strong_hold | 498 | 34.73% | 57.03 | +1.11 | 63.79 | 53.40 | 3.01% | 0 |
| first3_momentum_no_zone_break | 167 | 11.65% | 53.29 | +0.73 | 68.33 | 44.86 | 2.99% | 0 |
| first2_close_above_open_high | 114 | 7.95% | 50.88 | +0.33 | 65.91 | 41.43 | 3.51% | 0 |

相对 V288 baseline：

| 指标 | V288 open | V292 best |
|---|---:|---:|
| N | 1434 | 659 |
| WR | 52.86 | 56.60 |
| Avg | +0.51 | +1.09 |
| GAP_SL | 11.02% | 2.73% |
| 2025 WR | 52.63 | 62.21 |
| 2026 WR | 52.95 | 53.85 |
| 月度最低 WR | 39.31 | 38.36 |

结论：**次日 60m hold/continuation 确认方向比 open 追入更合理，可以显著降低 GAP_SL 并提高 Avg，但月度最低仍约 38%，未达生产。**

## 机制判断

1. V291 失败说明：同源 60m POI 一旦在次日被回踩，往往不是“回踩确认”，而是接管失败。
2. V292 改善说明：真正有价值的是接管后的持续性，而不是更低价位。
3. 但 V292 仍不够，因为它只是 entry-day 第一小时确认，缺少更原生的 15m/盘口/竞价级别“接管持续性”和板块扩散。

## 后续方向

不要继续做：
- V288/V292 上调 RR/hold 的出场调参；
- 把次日 POI limit 当生产入场；
- 用后验最佳月份/股票白名单接生产。

下一步只值得做：

`Market/Industry Regime → Same-source 60m takeover → Next-session 60m hold confirmation → 15m/盘口/竞价/成交额持续性 proxy → T+1 executable daily exit`

如果没有 15m/盘口/竞价数据，可继续在 60m 内做“前两小时成交额扩散 + 行业同行同步 + first60 open_to_confirm 1%-2%”的 no-write 组合验证，但这仍只是 proxy，不可直接生产。