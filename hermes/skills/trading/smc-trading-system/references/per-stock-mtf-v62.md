# V6.2 Per-Stock + Multi-Timeframe Analysis (2026-05-14)

## Per-Stock Results (40-param optimal: MW=7, SL=0.96, zone=lower)

Backtest on 4905 A-stocks with retrace entry for OB/Pinbar + immediate for FVG.

- 2183 stocks with ≥5 trades
- WR: min=0%, median=60%, max=100%
- Avg PnL: min=-4.0%, median=+1.6%, max=+8.1%
- 84 stocks with WR=100%
- 13 stocks with WR=0% (should be excluded from selection)

### Top 20 by WR (≥5 trades)

| Stock | Trades | WR | Avg PnL | Cum PnL |
|-------|--------|-----|---------|---------|
| 000006.SZ | 5 | 100% | +6.01% | +30.1% |
| 000020.SZ | 6 | 100% | +5.91% | +35.4% |
| 000063.SZ | 5 | 100% | +3.24% | +16.2% |
| 000541.SZ | 5 | 100% | +4.79% | +24.0% |
| 000582.SZ | 6 | 100% | +5.12% | +30.7% |
| 000682.SZ | 7 | 100% | +4.89% | +34.2% |
| 000683.SZ | 5 | 100% | +6.71% | +33.5% |
| 000778.SZ | 6 | 100% | +3.70% | +22.2% |
| 000913.SZ | 5 | 100% | +3.53% | +17.6% |
| 001286.SZ | 6 | 100% | +4.42% | +26.5% |
| 001299.SZ | 7 | 100% | +7.05% | +49.4% |
| 001318.SZ | 8 | 100% | +4.66% | +37.3% |
| 002177.SZ | 10 | 100% | +4.89% | +48.9% |

Data: `/root/.hermes/smc_opt_v21/per_stock_v62.json`

### Worst Stocks (WR=0%, ≥5 trades)

600436.SH, 600812.SH, 601236.SH, 603363.SH, 603648.SH,
603779.SH, 605056.SH, 605337.SH, 688212.SH, 688320.SH

These should be blacklisted in the scanner.

## Multi-Timeframe Analysis

60min data available for 93% of stocks (4551/4905) via Tencent ifzq API.

### 60min OB retrace (500 stocks test)

| Mode | Trades | WR | Avg PnL |
|------|--------|-----|---------|
| Daily OB retrace | 143 | 96% | +4.99% |
| 60min OB + Daily trend ✅ | 3 | 100% | +2.76% |
| 60min OB + No trend filter | 95 | 98% | +2.53% |

Conclusion: Daily >> 60min in per-trade PnL. Daily trend filter on 60min kills volume (only 3 trades). 60min can complement daily but daily is primary.

## Pinbar Retrace Validation

| Mode | Trades | WR | Avg PnL |
|------|--------|-----|---------|
| Pinbar Immediate | 4914 | 48.5% | +0.62% |
| Pinbar Retrace (MW=7, SL=0.96) | 3197 | 54.0% | +1.35% |

Pinbar retrace is effective (+5.5pp WR, +117% avg PnL). Pinbar behaves like OB: the pinbar low is a support zone; waiting for retrace to this level improves entry quality.
