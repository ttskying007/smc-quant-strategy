# V19 Backtest Engine — Critical Pitfalls and Fixes

## Pitfall 1: T+1 Assertion Order

The T+1 assertion (`exit_idx > entry_idx`) was placed BEFORE the EOD fallback, causing crashes when no TP/SL triggered during the walk-forward loop (exit_idx stays at -1).

**Wrong order:**
```python
assert exit_idx > entry_idx  # CRASH: exit_idx == -1
if exit_idx < 0:
    exit_idx = n - 1  # EOD fallback never reached
```

**Correct order:**
```python
if exit_idx < 0:
    exit_idx = n - 1  # EOD fallback FIRST
assert exit_idx > entry_idx  # THEN check
```

## Pitfall 2: Exit Price Inflation

Using `exit_price = max(bar['o'], tp_price)` for TP exits allows the exit to capture gap-up open prices far above the TP target. This inflated avg P&L from 4.14% to 18.40% in early V19.

**Fix:** `exit_price = tp_price` — cap at TP exactly.

## Pitfall 3: MAX_TP Cap Required

Without a MAX_TP cap, structural TP can be 10%+ above entry for stocks with large gaps. This creates misleading P&L when those distant TPs are hit.

**Fix:** `tp_price = min(tp_price, entry_price * 1.05)` — cap at 5%.

## Pitfall 4: MIN_PROJECTED_RR Too Strict

Using RR >= 1.5x filtered out 91% of trades on A-share daily because structural TP and SL distances are naturally similar (both 1.5-3%).

**Fix:** RR >= 1.0x (TP distance >= SL distance is sufficient).

## Pitfall 5: OB Dedup

Multiple OB_Bull signals can fire at the same swing point level, creating duplicate entries at the same price.

**Fix:** Track `entered_ob_bars` set and skip duplicate OB entries at same bar.

## Pitfall 6: Weekly Trend Filter Impact

Filtering out stocks with bearish weekly trend removes ~22% of stocks and ~24% of trades, but WR and P&L remain unchanged. This is the expected behavior — bearish weekly stocks produce entries that are borderline and get filtered by the RR filter anyway.
