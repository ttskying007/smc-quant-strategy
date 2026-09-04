# V12 Signal Correction — Pine Script Correctness Analysis (2026-05-11)

## Background

User Lei provided Pine Script reference code (Smart Money Concepts 2026, LuxAlgo SMC, Waves Ultimate) and explicitly rejected WR/RR optimization. Key requirement: **signal detection CORRECTNESS** — our signals must match what Pine Script produces, not generate better metrics.

## The 5 Core Defects in V11

| # | Defect | Impact | Fix |
|---|--------|--------|-----|
| 1 | **Swing detection lacks right confirmation** | 60%+ of "swings" are not actually structure points (later bars break the level) | `left=8, right=3` + ATR volatility inversion |
| 2 | **OB scans forward from every candle** | OB position offset 2-5 bars, causing 1-bar holds (entry at wrong location) | Scan BACKWARD from swing points |
| 3 | **No displacement filter** | Every bearish+impulse pair is an OB, even when price barely moved | Require `displacement > preceding_bar_range * mult` |
| 4 | **Sweep scans every candle's local window** | Sweeps detected at random locations, not at real structure points | Scan FROM swing points only (20-bar forward window) |
| 5 | **EQL is O(n^2) brute-force on all bars** | ~93% false signals, burying real equal highs/lows in noise | Compare only ADJACENT swing points (pivot-based) |

## Correct OB Detection Logic (Pine-compatible)

### Bullish OB (the most critical fix)

```
Wrong (V11):
  bar[i] is bearish → check bar[i+1..i+5] for bullish impulse → if yes, OB at i
  = every bearish candle before a green candle is an OB

Correct (V12, Pine-equivalent):
  swing_high exists at index S
  scan backward from S:
    Phase 1: skip pullback bars (bearish at the top)
    Phase 2: find the bullish impulse (consecutive green candles going up)
    Phase 3: the bearish candle BEFORE the impulse = Bullish OB
  = OB is where the SMART MONEY entered before the run-up to the swing high
```

### Displacement Filter

SMC 2026: `displacement = swing_price - ob_price`, require `displacement > range * 1.3`

Where:
- `swing_price` = the swing high/low that the impulse reached
- `ob_price` = the Order Block's low (bullish) or high (bearish)
- `range` = the OB bar's range (h - l)

### Swing Detection Parameters (tuned for 60min 200-bar data)

| Source | left | right | Comments |
|--------|------|-------|----------|
| Pine pivothigh (reference) | 10 | 10 | Too sparse for 200 bars (~3 swings) |
| V12 (60min hybrid) | 8 | 3 | ~12-16 swings in 200 bars, enough for OB+structure |
| Quick swings (entry helper) | 8 | 0 | For displacement calculation in hybrid mode |

## Key Implementation Details

### signals_v12.py Architecture

1. `detect_swings_v12(left=8, right=3)` — Pine-style with right confirmation
2. `detect_ob_v12()` — Two-pass hybrid: swing-backward + forward scan
3. `detect_structure_v12()` — State machine: HH/HL → BOS/CHOCH
4. `detect_sweep_v12()` — Swing-point level scanning (not per-candle)
5. `detect_eql_v12()` — Pivot-based adjacent swing comparison
6. `detect_fvg_v12()` — Same as V11 (FVG was already correct)
7. `detect_mss_v12()` — SMA crossover micro structure shift
8. Composite signals (BPR/IFVG/LV/RJ/OTE/PO3) — Same as V11 implementation

### Why V12 produces fewer trades than V11

- OB: Correct positioning filters out ~50% of V11's OBs that were at wrong positions
- Sweep: Only at real swing points, not every random candle break
- EQL: ~93% fewer signals (pivot-based is correct but sparse)
- CHOCH/BOS: State machine needs clear HH/HL patterns — same as V11

This is EXPECTED. Signal correctness > trade count. Incorrect signals produce bogus 1-bar holds.

### Running Backtests

```bash
cd /root/.hermes/scripts/v11
python3 -u test_v12_backtest.py
```

Results stored in `/root/.hermes/smc_opt_v12/`.

## User Communication Style

- Chinese native, direct technical communication
- Expects thorough multi-angle analysis before any change
- Explicitly rejected "指标优化" (metric optimization) — signal correctness is the ONLY valid objective
- When given reference code (Pine Scripts), expects deep comparison with specific impact assessment
- Catches inconsistencies and expects precision
- Values intellectual honesty about the agent's own limitations
- Will challenge on quality gaps between our implementations and proven reference implementations
