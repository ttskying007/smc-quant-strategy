# Retrace Entry Discovery & Validation (2026-05-14)

## Problem
Most entries buy at next-bar-open above the zone, causing excessive SL hits. 94% of OB entries buy above zone_low.

## Solution
Wait for price to retrace to zone_low before entering.

## Validation (2000 stocks)

| Signal | Method | WR | Avg PnL |
|--------|--------|-----|---------|
| OB_Bull | open | 93.5% | +3.92% |
| OB_Bull | retrace | 96.7% | +5.15% |
| FVG_Bull | open | 66.1% | +1.73% |
| FVG_Bull | retrace | 29.1% | +0.80% |
| Pinbar | open | 48.5% | +0.62% |
| Pinbar | retrace | 54.0% | +1.35% |

FVG retrace is HARMFUL (gap fill = bearish). OB/Pinbar retrace is beneficial.

## Optimal Params (40-grid, 2000 stocks)
MW=7, SL=0.96, zone=lower → OB WR=97.9% avg+4.61%

## V15 Dual-Engine Validation (2026-05-15)

Full 4905-stock V15 run confirmed retrace-only across both engines:

| Engine | Entry | Trades | WR | Avg PnL |
|--------|-------|--------|-----|---------|
| V13 | Zone retrace (age≤120) | 621 | 94.5% | +8.48% |
| V12 | Retrace + trend (age≤80) | 211 | **100.0%** | +9.94% |
| V12-old | Immediate (rejected) | 5,955 | 55.2% | +2.93% |

V12 immediate entry disaster: 40% stop rate from excessive SL distance. Retrace fix: zero stops. Trend filter alone cannot rescue bad entry timing.
