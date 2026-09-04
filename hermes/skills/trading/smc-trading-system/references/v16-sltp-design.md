# V16 SL/TP System Design

## Overview
Replaces V13's fixed SL/TP with a complete DynamicSLTP class.

## Components

### 1. Dynamic Stop Loss
```python
sl_buffer = atr_pct * (1.0 if state.volatile else 1.5)
sl = cost_line * (1 - sl_buffer)
```
- Based on **cost_line** (zone bottom), NOT entry price
- High volatility → tighter buffer (1.0×ATR) to lock profits
- Low volatility → wider buffer (1.5×ATR) to avoid noise stop-outs

### 2. Batch Take-Profit
```
TP1: entry × (1 + ATR% × 2.0) → 40% position
TP2: entry × (1 + ATR% × 4.0) → 30% position  
TP3: entry × (1 + ATR% × 6.0) → 30% position (trailing)
```

### 3. Trailing Stop (activates after TP2)
```python
trail_high = max(trail_high, bar_high)  # update high watermark
trail_stop = trail_high * (1 - ATR% × 0.8)
if bar_low <= trail_stop: exit
```
- Only activates after TP2 hit
- Trails 0.8×ATR below highest price since TP2

### 4. Per-bar update loop
```python
for each bar:
    result = sltp.update(bar_high, bar_low, bar_close)
    if result['action'] == 'sl': exit at loss
    if result['tp1']: lock 40% profit, continue
    if result['tp2']: lock 30% profit, activate trailing, continue
    if result['action'] == 'trailing': exit remaining 30%
    if result['action'] == 'tp3': exit at max target
```

## V16 Results with this SL/TP

| Engine | TP1 hit | TP2 hit | Trailing exit | SL hit |
|--------|---------|---------|---------------|--------|
| V16-SMC | 65% | 54% | 159/297 (54%) | 97/297 (33%) |
| V16-Trend | 92% | 76% | 91/119 (76%) | 9/119 (8%) |

Trailing exit dominates → system captures trend continuation after TP2.

## Key Design Decisions
1. SL based on cost_line (smart money entry), not entry price → proper risk management
2. Batch TP allows partial profit locking while letting winners run
3. Trailing activates only after TP2 → avoids premature exit on noise
4. Adaptive buffer based on market volatility → wider in calm markets, tighter in volatile
5. Max hold 30 bars → prevents stale positions

## Past Lessons (V13/V14)
- SL capped at fixed 8% was counterproductive (RR 1.07→0.94)
- tp_swing (exit at prior swing point) worse than ATR-based TP
- Simple trailing (always active) underperforms TP2-activated trailing
