# V7.1 Per-Stock & Time-Window Analysis

## 数据来源

`detailed_trades_v63.json` — 全量1328笔交易，1053只股票，17个月 (2024.09-2026.05)

## Per-Stock 表现

### Top 20 (by cumPnL, ≥3 trades)
603977.SH: 5t WR=100% avg+4.57% (best signal: OB_Bull)
600337.SH: 4t WR=100% avg+4.92%
603608.SH: 3t WR=100% avg+5.03% (best signal: Sweep_SSL→Pinbar)
300036.SZ: 4t WR=100% avg+4.26%

关键发现: 大量100%WR但仅3-5笔交易，统计显著性不足。
需要更多数据才能做个股精选池。

## 时间窗口分析

### 月度表现
| Month | n | WR | avgPnL |
|-------|---|-----|--------|
| 2025Q2 | 585 | 90.6% | +4.06% |
| 2025Q3 | 262 | 85.1% | +3.63% |
| 2025Q4 | 241 | 83.8% | +3.48% |
| 2026Q1 | 164 | 80.5% | +3.00% |
| 2026Q2 | 43 | 74.4% | +2.35% |

### 关键发现: 信号衰减
WR从2025Q2的90.6%衰退到2026Q2的74.4%。
可能原因:
1. 市场风格切换 (2025牛市 → 2026震荡)
2. 信号被市场消化 (alpha decay)
3. 2026Q2仅43笔，样本不足

## 多周期共振

### 周线MA趋势对日线入场影响
| Trend | n | WR | avgPnL |
|-------|---|-----|--------|
| bullish (MA20>MA50×1.02) | 430 | 90.9% | +4.15% |
| neutral | 406 | 86.0% | +3.64% |
| bearish (MA20<MA50×0.98) | 492 | 83.3% | +3.34% |

结论: 周线bullish时入场WR最高(+7.6pp vs bearish)。
但即使是bearish趋势，OB_Bull仍有83.3%WR — 因为OB本身包含结构验证。

## Gap分析

| Gap | n | WR | avgPnL | 主要信号 |
|-----|---|-----|--------|----------|
| 0 | 819 | 97.8% | +4.73% | OB_Bull (独立) |
| 1 | 275 | 67.6% | +1.85% | Sweep_SSL→FVG |
| 2 | 125 | 72.8% | +2.40% | Sweep_SSL→FVG |
| 3 | 109 | 66.1% | +2.06% | Sweep_SSL→FVG |

结论: gap=0 (OB独立) 最佳。gap越大，信号质量越差。

## 脚本

`/root/.hermes/scripts/v11/per_stock_v71.py`
输出: `/root/.hermes/smc_opt_v21/per_stock_v71.json`
