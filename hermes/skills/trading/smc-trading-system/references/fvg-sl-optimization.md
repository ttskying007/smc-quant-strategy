# FVG SL Optimization — 从宽止损到紧止损

## 问题

FVG_Bull (immediate entry) 使用 `find_sls()` 计算止损，SL率高达 32.3%，WR仅 67.5%。
相比之下 OB_Bull (retrace entry) 使用 `zone_low × 0.96` 紧止损，SL率仅 2.8%，WR=97.2%。

## 根因

`find_sls()` 返回结构止损（基于最近的摆动低点），在A股日线上通常距离入场价 2-5%。
结合 TP_CAP=1.05 (5%止盈)，大量交易的 RR 接近 1:1 边界，容易被市场噪音触发止损。

## 优化方案

对FVG也使用紧止损: `SL = zone_low × sl_mul` (与OB相同逻辑)。
zone_low 在 FVG 中 = entry_price (因为 FVG 没有真正的回调zone)。

## 网格搜索结果

| SL | TP | n | WR | avgPnL | SL率 | RR |
|----|----|---|-----|--------|------|-----|
| 0.95 | 1.05 | 70 | 80.0% | +3.03% | 18.6% | 4.2x |
| 0.96 | 1.05 | 241 | 73.0% | +2.44% | 26.6% | 3.3x |
| 0.97 | 1.03 | 328 | 75.6% | +1.54% | 24.4% | 3.1x |
| find_sls | 1.05 | 423 | 67.4% | +1.91% | 32.4% | — |

## 最优选择

**SL=0.95, TP=1.05**: WR=80.0%, SL率=18.6%, RR=4.2x (最佳质量)
**SL=0.96, TP=1.07**: WR=73.0%, SL率=26.6%, RR=3.3x (最佳平衡)

## 权衡

更紧的SL → 更高WR + 更低SL率 → 但更少交易通过RR≥1过滤器。
SL=0.95仅产生70笔交易 vs find_sls的423笔，但质量显著提升。

## 实现

已整合到 `backtest_v63_full.py`:
- retrace (OB/Pinbar): `SL = zone_low × sl_mul`
- immediate (FVG): `SL = fvg_zone_low × sl_mul` (= entry_price × sl_mul)

脚本: `/root/.hermes/scripts/v11/fvg_sl_opt.py`
