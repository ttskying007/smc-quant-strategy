# V42 — ATR-Adaptive Trailing System (6 Improvements)

## Overview

V42 replaces the fixed-threshold trailing in V38.4 with an ATR-adaptive system. Same entry logic as V38.4 (67,002 trades, 4,282 stocks), only the exit/trailing logic changed. Result: RR +10.3%, P&L +12%, Bear RR +27.9%.

## The 6 Improvements

### A) ATR-Adaptive Trailing Thresholds

All gain thresholds are scaled by ATR%:
```python
gain_breakeven = 0.20 * ATR%   # breakeven at 0.2×ATR
gain_lock01   = 0.30 * ATR%   # lock +0.1% at 0.3×ATR
gain_lock03   = 0.30 * ATR%   # lock +0.3% at 0.3×ATR  (actually 0.2×1.5×1.0)
gain_lock15   = 0.60 * ATR%   # lock +1.5% at 0.6×ATR
gain_lock30   = 1.20 * ATR%   # lock +3.0% at 1.2×ATR
```

With grid-optimal multipliers: breakeven_mult=0.20, lock_mult=0.50
- Low-ATR stocks (<1%): tighter trailing, exit faster
- High-ATR stocks (>3%): looser trailing, let trends run
- Formula: `min(0.3, max(0.5, ATR_pct))` used as safe_atr minimum

### B) Structure Proximity Awareness

When price approaches a swing high (bull) or swing low (bear), trailing tightens:

```python
lookahead = min(30, len(t.ohlcv) - bar_idx - 1)
atr = calc_atr_v38(ohlcv, bar_idx)
prox_factor = 2.0  # Within 2×ATR of structure
tighten = 0.75     # Tighten by 25% max

dist = (swing_price - entry_price) / entry_price * 100
if 0 < dist < atr * prox_factor:
    proximity = 1.0 - (dist / (atr * prox_factor))
    struct_tight = 1.0 - (proximity * (1 - 0.75))  # 0.75-1.0 range
```

Applied as: `tight_gain = gain * struct_tight`

### C) Wyckoff Phase-Aware Multipliers

Each phase has an independent effective multiplier (>1 = looser, <1 = tighter):

| Phase | Multiplier | Effect |
|-------|-----------|--------|
| Markup | 1.20 | Looser (let trends run) |
| Accumulation | 1.10 | Slightly looser |
| Reaccumulation | 1.00 | Neutral |
| Distribution | 0.75 | Tighter (protect profits) |
| Unknown | 1.00 | Neutral |

Applied as: `eff_mult = phase_mult * bear_mult`

### D) Volume-Confirmed Exit

On SL-break detection, check volume before exiting:

```python
ratio = break_vol / avg_vol(20 bars)
if ratio >= 1.2:          # Volume spike = real break → exit
    confirmed = True
elif ratio <= 0.6:        # Low volume = possible fake → wait 1 bar
    confirmed = False
else:                     # In between → exit if ratio >= 0.8
    confirmed = (ratio >= 0.8)
```

Only applied to trades WITH a structure TP (tight/noTP profile exits immediately regardless of volume).

### E) Per-Stock Parameter Grid Search

9-parameter grid over 200 stocks on saved entries (Phase 2 — re-run trailing only):

```python
GRID = {
    'breakeven_mults': [0.20, 0.30, 0.40],
    'lock_mults': [0.50, 1.00, 1.50],
}
```

Results (200 stocks, 2888 trades):
| BE | LK | WR | RR | EV |
|----|----|----|----|----|
| 0.20 | 0.50 | 87.6% | 7.15x | 6.26 |
| 0.30 | 0.50 | 85.4% | 7.20x | 6.15 |
| 0.40 | 0.50 | 83.1% | 7.23x | 6.00 |

Best: BE=0.20, LK=0.50 (tightest breakeven, loosest lock multipliers). KEy: early breakeven protects capital, wider lock thresholds let trend trades run.

### F) Bear Differentiated Trailing

Bear direction has independent thresholds via `bear_mult = 0.75`:
- Effective gain thresholds are 25% tighter than bull
- Bear trailing locks profits faster (bear direction has inherent upward drift resistance)
- Combined with phase multiplier for distribution-phase bear trades: 0.75 × 0.75 = 0.56 (very tight)

## Implementation Pattern (Monkey-Patching)

The V42 trailing replaces V38's `calc_v38_trailing` via monkey-patching:

```python
import v11.rolling_backtest_v38 as rb38

# 1. Define V42 trailing function with same signature
def my_trailing(ohlcv, entry_idx, entry_price, initial_sl,
                structural_tp, n, max_hold, direction):
    ...  # Reads context from a module-level _CTX object

# 2. Replace the function in the module
rb38.calc_v38_trailing = my_trailing

# 3. Wrap backtest to set context per stock
_orig_backtest = rb38.backtest_stock_v38
def _patched_backtest(ohlcv, symbol):
    # Set _CTX.phase, _CTX.tree, _CTX.config
    return _orig_backtest(ohlcv, symbol)
rb38.backtest_stock_v38 = _patched_backtest
```

**CRITICAL**: Python function name resolution for same-module calls happens in the module's global namespace AT CALL TIME. So `rb38.calc_v38_trailing = my_trailing` correctly redirects calls from `evaluate_v38_entry` (which calls `calc_v38_trailing` internally).

**Pitfall**: Do NOT double-process. If the monkey-patched trailing already ran inside `backtest_stock_v38`, do NOT re-run trailing on the returned trades — the results are already correct.

## Results (Full 4800)

| Metric | V38.4 | V42 | Change |
|--------|-------|-----|--------|
| WR | 90.6% | 91.3% | +0.7pp |
| RR | 7.98x | 8.80x | +10.3% |
| PF | 114 | 114 | = |
| P&L | +3.50% | +3.92% | +12.0% |
| Bull RR | 9.36x | 9.82x | +4.9% |
| Bear RR | 5.42x | 6.93x | +27.9% |
| Bear WR | 84.6% | 89.1% | +4.5pp |
| TP/TR | 44.9/55.1 | 53.2/46.8 | more TP hits |

## Files

- `/tmp/v42_full.py` — Standalone V42 engine + full 4800 scanner
- `/tmp/v42_system.py` — V42 200-stack test + grid search (Phase 1+2)
- `/root/.hermes/smc_opt_v38/v42_full.json` — Full 4800 results (67,002 trades)
- `/root/.hermes/smc_opt_v38/v42_trailing_optimization.json` — Grid search results
