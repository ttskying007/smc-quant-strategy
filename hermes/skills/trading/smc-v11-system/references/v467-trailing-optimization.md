# V467 Trailing Optimization — Progressive BE Lock + TP-Distance Awareness

## Problem Statement

V465 used hard `MULTI_BAR_BE_LOCK=2` which forced breakeven exit on any trade still at entry price after 2 bars. Data showed this killed 152 trades (43% of multi-bar holds) prematurely — many would have developed into +10.95% avg winners.

## Root Cause: The SL Tightness Paradox

From V467 full scan (1472 trades):

| SL Threshold | Trades | WR | RR | P&L |
| SL <= 0.2% | 519 | 87.3% | 24.93x | +4.00% |
| SL <= 0.3% | 850 | 84.6% | 22.70x | +4.26% |
| SL > 0.5% | 410 | 75.6% | 6.02x | +5.12% |

Tighter SL = higher RR but lower absolute P&L. The hard BE-lock was the wrong tool — it protected P&L but at the cost of RR and winners.

## TP Distance Reliability Curve

| TP Range | Trades | WR | Avg RR | Avg Hold |
| TP 0-3% | 46 | 100% | 8.16x | 1.0 |
| TP 3-5% | 129 | 100% | 12.66x | 1.0 |
| TP 5-8% | 392 | 100% | 16.76x | 1.0 |
| TP 8-12% | 367 | 100% | 20.26x | 1.0 |
| TP 12-20% | 333 | 58% | 16.41x | 2.7 |
| TP 20%+ | 205 | 38% | 13.64x | 5.7 |

Breakpoint at 12%: TP<=12% is perfectly reliable (100% WR), TP>12% is unreliable (WR 38-58%).

## Multi-Bar Trade Analysis

- Multi-bar (hold>=3) trades: 275 (18.7% of total)
- Multi-bar WR: 52.4%
- Multi-bar avg PnL when winning: +10.95%
- Multi-bar avg hold when losing: 5.2 bars
- Avg SL of losing multi-bar trades: 0.65% (too wide)

## V467 Design: Two Innovations

### 1. Progressive BE Lock (replaces hard MULTI_BAR_BE_LOCK)

PROGRESSIVE_BE = [(3, 0.0), (5, 0.3), (8, 0.5), (12, 1.0)]
  hold>=3 AND gain<0%    -> lock SL to entry (breakeven)
  hold>=5 AND gain<0.3%  -> lock SL to entry
  hold>=8 AND gain<0.5%  -> lock SL to entry
  hold>=12 AND gain<1.0% -> lock SL to entry

Implementation in calc_v38_trailing (bull branch, after TP proximity check):

  if tp_price and tp_pct and tp_pct > TP_RELIABLE_MAX:
      # Far TP (>12%): only lock at hold>=5 with negative gain
      if j >= entry_idx + 5 and gain_pct < 0:
          sl = max(sl, entry_price)
  else:
      for min_hold, min_gain in PROGRESSIVE_BE:
          if j >= entry_idx + min_hold and gain_pct < min_gain:
              sl = max(sl, entry_price)
              break

### 2. TP-Distance-Aware Trailing

TP_RELIABLE_MAX = 12.0
  TP<=12%: reliable target, use tighter trailing
  TP>12%: unreliable (WR drops to 58-38%), give more room

## Results: V465 (hard lock) vs V467 (progressive)

| Metric | V465 | V467 | Change |
| WR | 81.9% | 82.7% | +0.8pp |
| RR | 16.49x | 16.72x | +1.4% |
| P&L | +4.52% | +4.58% | +1.3% |
| Multi-bar trades | 255 (17.3%) | 275 (18.7%) | +20 |
| Flat exits | 152 | 104 | -32% |
| Big wins (PnL>10%) | 91 | 97 | +6 |

## Configuration

MIN_PROJECTED_RR = 8.0       # Skip trades with projected RR < 8x
PROGRESSIVE_BE = [(3, 0.0), (5, 0.3), (8, 0.5), (12, 1.0)]
TP_RELIABLE_MAX = 12.0       # TP>12% gets looser trailing
MAX_HOLD = 80                # 60min: ~5 trading days
