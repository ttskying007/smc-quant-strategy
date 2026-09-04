---
name: smc-engine-v40
description: SMC V40 Portfolio Backtest — Quality-Weighted Position Sizing. 基于V38.3逐笔数据(67,002笔, 4,282只), 按WR分档浮动杠杆, 组合级P&L分析.
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [smc, portfolio, position-sizing, backtest, trading]
---

# SMC V40 — Portfolio Backtest with Quality-Weighted Position Sizing

## Overview

On top of V38.3 per-trade data from `backtest_v38_full.json` (67,002 trades, 4,282 stocks), applies quality-weighted position sizing and computes portfolio-level metrics.

## WR Buckets & Multipliers

| WR Range | Label | Multiplier | Max Position |
|---|---|---|---|
| ≥92% | elite | 1.75x | 1.75% |
| 85-92% | high | 1.35x | 1.35% |
| 75-85% | baseline | 1.00x | 1.00% |
| 60-75% | medium | 0.75x | 0.75% |
| 40-60% | low | 0.35x | 0.35% |
| <40% | penalty | 0.10x | 0.10% |

RR bonus: elite with RR≥5.0 gets +15%, high with RR≥4.0 gets +8%.

## Usage

```bash
cd /root/.hermes/scripts/v11
PYTHONUNBUFFERED=1 python3 portfolio_v40.py
```

## V40 Key Results

- **Equal-weight (1% each)**: +2242.75% portfolio P&L
- **Quality-weighted**: +3848.29% portfolio P&L (+71.6% improvement)
- **Quality premium**: +1605.54%
- **Elite bucket** (WR≥92%, 2503 stocks): contributes 68% of total P&L at avg 1.99% position
- **Best entry type**: OB (+2033.06%), FVG (+1749.23%)
- **Direction**: Bull 78.6%, Bear 21.4%
- **Monte Carlo (500 sims)**: Expected return +3849%, std 16.81%, 100% positive, VaR(95%) -3821%

## Files

- Script: `/root/.hermes/scripts/v11/portfolio_v40.py`
- Output: `/root/.hermes/smc_opt_v40/v40_portfolio.json`
- Input data: `/root/.hermes/smc_opt_v38/backtest_v38_full.json` (33MB, V38.3 per-trade)

## Limitations

- WR-based quality uses full-history WR (future-aware). Real trading would need rolling WR.
- No chronological portfolio curve — trades don't have date info.
- Assumes all trades can be executed independently without capital constraints at 1.69% avg position.
