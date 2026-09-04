# V20 Diagnostic Fixes — Full Root Cause Analysis (2026-05-13)

## Diagnostic Methodology

7 representative stocks traced: 600519(茅台), 000001(平安), 300750(宁德), 600036(招行), 000858(五粮液), 688981(中芯), 002594(比亚迪).

Each signal type independently called + counted. Swing detection via `detect_leg_swings(ohlcv, leg_size=20)`.

## Fix 1: OB(SMC) — 0 output for ALL stocks

**Root cause**: `detect_ob_smc2026` line 277: `disp > rng * 0.6` AND `strength >= 2.0`.
A-share daily displacement relative to ATR is too small (茅台 ATR=24, single candle displacement ~3-5).

**Fix**: `disp > rng * 0.25`, `strength >= 1.0` (both lines 277, 301 in signals_v19.py).
**Result**: 0 → 4 OB per stock (600519: 2 Bull + 2 Bear).

## Fix 2: CHOCH/BOS — crossed flag permanent lock

**Root cause**: `detect_choch_bos_v19` line 162: `sh.crossed = True`. Each swing fires AT MOST ONCE.
39-50% of swings never get their price crossed by any subsequent close → permanently dead.

**Fix**: `detect_choch_bos_v20` — removed crossed flag. At each bar, find most recent unviolated swing high/low (any later swing of same type with more extreme price "beats" it). Check crossover/crossunder. Uses `last_cross_dir` to determine CHOCH (direction change) vs BOS (continuation).

**Key insight**: Must pick MOST RECENT unviolated swing (highest bar_idx), NOT highest price swing. Original V20 picked highest price → always the all-time-high → rarely crossed.

## Fix 3: Sweep — near-zero detection

**Root cause**: `detect_sweep_v19` line 364: `min_pen = max(atr*0.15, avg_price*0.001)`. Window = 30 bars.
Swing points are spaced ~17 bars apart (18 swings / 300 bars). Only 0-2 pierce opportunities per stock.

**Fix**: `detect_sweep_v20`: `min_pen = max(atr*0.08, avg_price*0.0005)`. Window = 60 bars.
**Result**: 600519: 4→11, 000001: 0→7, 300750: 0→11.

## Fix 4: EQL/EQH — adjacent-only comparison

**Root cause**: `detect_eql_v19` compares only `highs[i]` vs `highs[i-1]`. 0.5% fixed threshold:
- 茅台 0.5% = 7.13 元 (reasonable)
- 平安 0.5% = 0.056 元 (too strict for low-price)

**Fix**: `detect_eql_v20`: O(n²) all-pair comparison. Threshold = `max(avg_price * 0.003, atr_val * 0.5)` — ATR-adaptive.
**Result**: 600519: 3→13, 000001: 1→5.

## Fix 5: MSS — excessive cooldown

**Root cause**: `detect_mss_v19`: cooldown = 12 bars (max ~25/300 bars). Window = 40 bars.

**Fix**: `detect_mss_v20`: cooldown = 5 bars. Window = 50 bars.
**Result**: 600519: 3→5, 000858: 5→8.

## Fix 6: Sequence window ATR adaptation

**Root cause**: All 16 patterns used fixed 2-5 bar gaps. High-vol stocks (宁德 ATR=4.26%) move fast, low-vol (招行 ATR=1.23%) move slow.

**Fix**: `_build_sequences(atr_pct)`:
```python
scale = max(0.5, min(2.0, 1.5 / max(atr_pct, 0.005)))
windows = [max(1, int(w * adj_scale)) for w in base_windows]
```
High ATR% → shorter windows. Added 12 new patterns (MSS→FVG→OB, BOS→FVG→OB, CHOCH→OB).

**Result**: Sequences: 393→3,711 (+844%), stocks: 332→2,562 (+672%).

## Rejected Fixes

**CHOCH/BOS trend_bias removal**: V20 correctly only calls CHOCH when direction genuinely changes (last_cross_dir flips). In 300-bar windows, trend changes are rare → low CHOCH count is expected and CORRECT. V19 artificially inflated CHOCH via fixed trend_bias=0 initial state.
