# Trailing Stop PnL Verification Methodology

## When to Use

When backtest trades show PnL clustering at a specific percentage (e.g., 50% of trades at exactly 13.42%), before claiming "fixed R-multiple bug":

1. Verify the actual exit price is consistent with the trailing stop price
2. Verify the trailing stop mechanism is computing real prices, not a constant

## Verification Steps

### Step 1: Check exit_legs

Each V59/V64 trade has `exit_legs` — a list of partial/full exit stages. A healthy trailing-stop exit looks like:

```json
{
  "exit_legs": [
    {"reason": "TP1_HIT", "weight": 0.05, "price": 17.33, "pnl_pct": 5.48},
    {"reason": "TP2_HIT", "weight": 0.05, "price": 18.35, "pnl_pct": 11.69},
    {"reason": "STRUCT_PENDING_BREAK", "weight": 0.0, "price": 17.80, "stop": 18.83},
    {"reason": "STRUCT_CONFIRM_BREAK", "weight": 0.9, "price": 18.83, "pnl_pct": 14.61}
  ]
}
```

Key evidence the stop is **REAL** (not fixed):
- The `stop` field in pending/confirm break legs tracks the **actual trailing stop price**
- The stop price changes across legs (e.g., initial stop → after trend run → structure break)
- Trend-promoted trades (trend_runner=true) have stop prices much higher than non-promoted trades

### Step 2: Verify PnL = (stop_price / entry_price - 1) × 100

For each STRUCT_CONFIRM_BREAK leg:
```
expected_pnl = (leg['price'] / entry_price - 1) × 100
reported_pnl = leg['pnl_pct']
```

If `abs(expected_pnl - reported_pnl) < 0.1`, the PnL IS based on actual stop price.

### Step 3: Check R-multiple distribution

Sort trades by `trend_runner` status:

| Group | Expected R | Explanation |
|-------|-----------|-------------|
| trend_runner=false | ~4.0R | after_2r_lock_r=4.0 — stop locked at 4×risk after 2R achieved |
| trend_runner=true | 4–11+R | stop keeps trailing with structure — strong trends much higher |

This distribution is correct behavior, NOT a bug. The 4.0R lock prevents 2R→0R giveback after partial TP hits.

### Step 4: Check exit_reason distribution

- STRUCT_CONFIRM_BREAK = 124/137 (90.5%) — ALL positive → expected (stop trails above entry once price moves up)
- SL_HIT = 10/137 — all negative → expected (initial stop hit when entry was wrong)
- GAP_SL_HIT = 2/137 — all negative → expected (gap through initial stop)
- TP_HIT = 0/137 — partially misleading (TP1/TP2 partial hits exist in exit_legs but final exit reason is always STRUCT_CONFIRM_BREAK)

### Step 5: Compute weighted average

For trades with partial hits:
```
total_pnl = Σ(leg['weight'] × leg['pnl_pct'])  # only legs with weight > 0
```

This must match the trade's `pnl_pct` field.

## Why 13.42% Clustering Is NOT a Bug

The clustering is a mathematical consequence of the exit plan parameters:

```
v53_exit_params:
  tp1_frac=0.05, tp1_r=1.5    → 5% at 1.5R (e.g., 5.25% for 3.5% risk)
  tp2_frac=0.05, tp2_r=3.2    → 5% at 3.2R (e.g., 11.20% for 3.5% risk)
  after_2r_lock_r=4.0         → 90% at 4.0R (e.g., 14.00% for 3.5% risk)

Weighted total = 5.25×0.05 + 11.20×0.05 + 14.00×0.9 = 13.4225%
```

For risk_pct=3.5% (common in V66 due to A_NORMAL quality tier), this gives exactly 13.42%. This is correct behavior — all non-trend-runner trades exit at 4.0R lock.

## Pitfalls

- ❌ Jumping to "fixed R-multiple bug" based only on PnL histogram clustering
- ❌ Not checking exit_legs to see stop prices
- ❌ Not separating trend_runner trades (4-11+R) from non-trend-runner trades (~4.0R)
- ✅ Always verify PnL = (stop_price/entry-1) before claiming a backtest artifact
