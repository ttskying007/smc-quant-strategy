# V26 SL/TP RR Optimization

## Problem
V26.0 had RR=1.07x (avg_win=2.60%, avg_loss=2.42%) — nearly 1:1 risk/reward.
Root causes:
1. 27 losses with SL < 0.5% (avg 0.2%) — effectively no stop
2. TP1 using nearest resistance — too close, small wins
3. Trail activating at 0.8R — cut winners too early

## Fixes Applied

### 1. Minimum SL Floor
```python
MIN_SL_PCT = max(atr_pct * 0.5, 1.5)
if sl_pct_raw < MIN_SL_PCT:
    sl_price = entry_price * (1 - MIN_SL_PCT / 100)
```
Effect: 0 sub-1.5% stops, 27 micro-losses eliminated

### 2. TP1 RR ≥ 1.5 Floor
```python
for r in resistances:
    r_pct = (r - entry_price) / entry_price * 100
    if r_pct >= sl_pct * 1.5:  # RR ≥ 1.5
        tp1_price = r
        break
```
Effect: skip nearest resistance if RR inadequate

### 3. Wider Structural Lookback
`lookback=60 → lookback=120` for resistance detection

### 4. Delayed Trail Activation
```
Trail: 0.8R → 1.5R (TREND_UP/HIGH_VOL), 0.6R → 1.2R (TREND_DOWN)
```
Effect: let winners run 2x farther before trail kicks in

## Results
| Metric | Before | After | Change |
|--------|--------|-------|--------|
| RR | 1.07x | 1.89x | +77% |
| avg Win | +2.60% | +6.81% | +162% |
| avg Loss | -2.42% | -3.60% | wider SL cost |
| TP1 hit | 70% | 51% | fewer but bigger |
| Trail exit | 73% | 78% | more trail exits |

## Key Lesson
When RR < 1.5, check three things in order:
1. Is SL too tight? (enforce min SL ≥ 1.5%)
2. Is TP too close? (skip nearest resistance, use RR floor)
3. Is trail cutting winners? (delay activation to 1.5R+)
