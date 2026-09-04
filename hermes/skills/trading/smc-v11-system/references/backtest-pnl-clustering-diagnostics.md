# Backtest PnL Clustering Diagnostics

When a backtest report shows suspicious PnL clustering (e.g., 50% of trades at exactly 13.42%), determine whether it's a real exit-simulation bug or a legitimate consequence of exit-plan parameters.

## Signal: Suspicious Clustering

- PnL values all cluster at one or two decimal-precise values (13.42, 14.01, -3.50)
- Q25 ≈ Q75 (PnL distribution has almost no spread)
- STRUCT_CONFIRM_BREAK is the sole exit reason for all positive trades
- SL_HIT exits have PnL exactly matching risk_pct (−3.50% when risk=3.5%)

## Step 1: Check exit_legs

Load a trade's `exit_legs` array. A healthy backtest should show:

```
[
  {reason: "TP1_HIT", price: 4.72, weight: 0.05, pnl_pct: 5.25},
  {reason: "TP2_HIT", price: 4.98, weight: 0.05, pnl_pct: 11.2},
  {reason: "STRUCT_CONFIRM_BREAK", price: 5.11, weight: 0.9, pnl_pct: 14.0, stop: 5.11}
]
```

**Bug signal**: STRUCT_CONFIRM_BREAK leg has `pnl_pct` that cannot be verified from `(stop_price / entry_price - 1) * 100`. The stop_price might be missing or the pnl is hardcoded.

**Healthy signal**: pnl_pct = (stop_price / entry_price - 1) * 100 within floating-point precision. Verify for at least 3 trades.

## Step 2: Check trailing stop parameters

Look for exit-plan parameters on the trade:

```python
v53_exit_params = {
    'after_2r_lock_r': 4.0,     # After 2R profit, lock stop at 4R
    'tp1_r': 1.5,                # TP1 = 1.5 × risk → 5.25% PnL
    'tp2_r': 3.2,                # TP2 = 3.2 × risk → 11.2% PnL
    'tp1_frac': 0.05,            # 5% weight on TP1
    'tp2_frac': 0.05,            # 5% weight on TP2
}
```

If `after_2r_lock_r` exists, the 4.0R exit is a design choice, not a bug. The weighted average is:
```
PnL = TP1_pct × 0.05 + TP2_pct × 0.05 + (after_2r_lock_r × risk) × 0.9
```

For risk=3.5%: 5.25×0.05 + 11.2×0.05 + 14.0×0.9 = **13.4225%** ← exactly the observed cluster

## Step 3: Compare trend_runner vs non-trend-runner

Split trades by `trend_runner` flag and compute average R-multiple at exit:

| Group | N | Avg Exit R | Spread |
|-------|---|-----------|--------|
| trend_runner=true | 55 | 8.87R | Wide |
| trend_runner=false | 166 | 4.10R | Tight (~4.0R) |

**Bug signal**: Both groups have identical R-multiple (all at 3.83x regardless of trend state).

**Healthy signal**: trend_runner=true trades show higher R-multiple with genuine spread. Non-trend-runner trades cluster near `after_2r_lock_r` because structure breaks before the stop can trail higher — this is expected behavior in range-bound exits.

## Step 4: Verify PnL from actual trailing stop price

For non-trend-runner trades, the STRUCT_CONFIRM_BREAK exit price should equal the trailing stop level. Compute:
```python
exit_pnl = (exit_leg.STRUCT_CONFIRM_BREAK.price / entry_price - 1) × 100
expected_pnl = after_2r_lock_r × risk_pct
```

If `exit_pnl ≈ expected_pnl` for 90%+ of non-trend-runner trades, the mechanism is consistent and real.

## Common Pitfalls

| PnL Symptom | Likely Cause |
|---|---|
| One exact value covers 40-50% of trades | after_2r_lock_r design, not bug |
| Zero variation at all (100% at same value) | Hardcoded R-multiple bug |
| Pattern persists across trend_runner groups | Definite bug — stop not trailing |
| PnL values are round numbers (10.0, 20.0, 30.0) | Price-agnostic fixed PnL |
| PnL values match risk×3.83 exactly per trade | after_2r_lock_r=4.0 with rounding |
