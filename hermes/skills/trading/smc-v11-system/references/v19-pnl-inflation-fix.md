# V19 P&L Inflation Root Cause & Fix

## Symptom

V19 backtest reported avg P&L +18.40% per trade with 1.1 bar hold — impossible for A-share 10% daily limit.

## Root Cause

The V18 backtest engine's exit logic captured gap premiums:

```python
# BUG: exit at max(open, TP) inflates P&L
if bar['h'] >= tp_price:
    exit_price = max(bar['o'], tp_price)  # captures gap above TP
```

If a stock opens 5% above yesterday's close and the TP is only 3% above entry, the `max()` captures the full 5% gap instead of exiting at TP.

## Fix

```python
# FIX: exit at TP price exactly
if bar['h'] >= tp_price:
    exit_price = tp_price  # no gap capture
```

Same for SL: `exit_price = sl_price` instead of `min(bar['o'], sl_price)`.

## Impact

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| Avg P&L | +18.40% | +9.70% |
| Trades | 38,770 | 19,103 |

Additional MIN_PROJECTED_RR filter (RR >= 1.0) reduced trades by 50%.
