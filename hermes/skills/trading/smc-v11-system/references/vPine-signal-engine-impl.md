# V-Pine Signal Engine Implementation Details

## Overview

Built 2026-05-11. Complete rewrite of signals_v11.py with 4 Pine Script quality improvements. Derived from 3 reference scripts (Smart Money Concepts 2026, LuxAlgo SMC, Waves Ultimate). ~2000 lines, same interface as V11.

## Core Architecture

```
detect_swings_vPine(left=10, right=10)  → Pine-quality swings
    ↓
    ↓ (passed to OB, Structure, Sweep, EQH)
    ↓
detect_ob_vPine(swing_mode='hybrid')   → OB with displacement filter
detect_structure_vPine(swings, fallback=V11) → State machine BOS/CHOCH
detect_eql_vPine(pivot_length=4)        → Pivot-based EQH/EQL
detect_fvg_vPine()                      → Same as V11, ATR-normalized min_width
detect_sweep_vPine()                    → Same as V11, with Pine swings
(all other signals identical to V11)
```

## Key Implementation Bugs Found During Build

### Bug 1: Pine swings too sparse
The `detect_swings_vPine(left=10, right=10)` requires 10 bars of right confirmation. In 200 bars of data, this produces only ~8 swings. This is correct Pine Script behavior, but downstream consumers (state machine, displacement calc) need more points.

**Fix**: Quick swings (`_find_swing_highs_vPine(lookback=8)`, no right confirmation) for displacement calc; Pine swings for structure.

### Bug 2: `for...else` loop preventing displacement calculation
```python
# WRONG: else block never runs because price always breaks below OB within 20 bars
for k in range(i + 2, min(i + 20, n)):
    if ohlcv[k]['l'] < bar['l']:
        break  # ← always triggers within 1-2 bars
else:
    # This code NEVER executes
    local_swing = find_nearest_swing(...)
```

**Fix**: Remove the for-else guard. Directly find nearest forward swing via `for sw_idx, sw_price in swing_lows: if sw_idx > i: local_swing = sw_price`.

### Bug 3: Bearish OB displacement direction
```python
# For bearish OB, displacement should be from OB_high to forward swing HIGH
local_swing - bar['h']  # WRONG if local_swing is a swing LOW

# Correct: look for forward swing HIGH
displacement = bar['h'] - next_swing_high  # positive = bearish displacement
```

### Bug 4: metadata keys not at `s['metadata']` level
`Signal.to_dict()` uses `**self.metadata` which SPREADS metadata keys to the top-level dict. When debugging, check `s.get('displacement_ratio', 0)` not `s.get('metadata', {}).get('displacement_ratio', 0)`.

### Bug 5: EQL pivot-based vs V11 brute-force
V11 does O(n^2) pairwise comparison of ALL bars, finding 5663 EQL signals in 200 stocks. V-Pine compares only adjacent SWING points, finding 399. The V11 approach produces near-100% false positives (every two similar bars = EQL). The Pine approach is correct.

## Hybrid Mode Design

The OB displacement filter has three modes:

1. **swing_only** (strict Pine quality): Only scan 5-15 bars backward from swing points. Produces ~3 OBs per stock with high displacement_ratio.

2. **hybrid** (default): swing-only + full-data scan with displacement fallback. Same count as V11 but each OB has displacement_ratio metadata.

3. **full**: Scan all candles like V11 with displacement ratio. Used when swing_data is unavailable.

## Displacement Ratio Fallback

When no swing point exists within 25 bars of an OB candle:

```python
# Bullish OB: use 10-bar forward price range as displacement proxy
next_high = max(b['h'] for b in ohlcv[i+2:i+12])
displacement = next_high - bar['l']

# Bearish OB: use 10-bar forward low
next_low = min(b['l'] for b in ohlcv[i+2:i+12])
displacement = bar['h'] - next_low
```

This is less precise than swing-based displacement (because the forward range might be noise) but prevents displacement_ratio=0 for valid OBs.

## V470 Engine Integration

v470_engine.py is a copy of v468_engine.py with one import changed:
```python
# OLD: from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds
# NEW:
from v11.signals_vPine import detect_all_signals_vPine as detect_all_signals_v11, calc_adaptive_thresholds
```

No other changes needed because the interface is identical.

## Full 4552 Results

| Metric | V468 | V470 | Δ |
|--------|------|------|---|
| Stocks | 561 | 452 | -19.4% |
| Trades | 1318 | 1056 | -19.9% |
| WR | 58.0% | 57.7% | -0.5% |
| RR | 5.64x | 6.37x | +12.9% |
| P&L/笔 | +2.42% | +2.52% | +4.1% |

Time: 67s vs 87s (23% faster, fewer swing calculations needed).

## Files

- `/root/.hermes/scripts/v11/signals_vPine.py` — Signal engine (~2000 lines)
- `/root/.hermes/scripts/v11/v470_engine.py` — V470 engine (copied from v468, import changed)
- `/root/.hermes/scripts/v11/test_vPine_signals.py` — Signal quality comparison test
- `/root/.hermes/scripts/v11/test_ob_disp.py` — OB displacement diagnostic
- `/root/.hermes/scripts/v11/test_v470_200.py` — V470 200-stock test
- `/root/.hermes/scripts/v11/test_v470_full.py` — V470 full 4552 scan
- `/root/.hermes/smc_opt_v470/` — Results (v470_full_trades.json, v470_full_stocks.json, v470_summary.json)
