# V19 Signal Detection Quality Audit (2026-05-13)

Deep code-level diagnostic of all 7 signal types in `signals_v19.py`, tracing root causes of under-detection and inaccuracy.

## Diagnostic Script

`/root/.hermes/scripts/v11/signal_diag.py` — reusable diagnostic that prints per-stock signal counts, root cause analysis, and uncrossed swing points.

## Test Stocks and Summary

7 representative stocks across market cap and price ranges:

| Stock | Swings | CHOCH+BOS | Sweep | MSS | EQL/EQH | OB(SMC) | Total Signals |
|-------|--------|-----------|-------|-----|---------|---------|---------------|
| 600519 茅台 | 18 | 11 (61%) | 4 | 3 | 3 | **0** | 42 |
| 000001 平安 | 11 | 5 (45%) | 0 | 4 | 1 | **0** | 23 |
| 300750 宁德 | 11 | 7 (64%) | 0 | 2 | 1 | **0** | 23 |
| 600036 招行 | 9 | 5 (56%) | 0 | 1 | 0 | **0** | 25 |
| 000858 五粮液 | 14 | 8 (57%) | 3 | 5 | 1 | **0** | 38 |
| 688981 中芯 | 8 | 4 (50%) | 1 | 1 | 0 | **0** | 15 |
| 002594 比亚迪 | 12 | 6 (50%) | 1 | 1 | 1 | **0** | 53 |

## Root Cause 1: OB(SMC) COMPLETELY DEAD — `detect_ob_smc2026` returns 0 for ALL stocks

**Location**: `signals_v19.py` lines 259-314

**Code**:
```python
for i in range(7, 18):
    idx = sl_bar - i
    bar = ohlcv[idx]
    if bar['c'] < bar['o']:  # Bearish candle before bullish impulse
        disp = sl_price - bar['l']
        rng = bar['h'] - bar['l']
        if rng > 0 and disp > rng * 0.6:
            strength = min(10.0, disp/atr*2 + rng/atr*1.5)
            if strength >= 2.0:
```

**Why it fails**: A-share daily bars have displacement relative to ATR that's too small. For 茅台 (ATR=24.16): typical reverse candle has displacement ~3-5, range ~15, so `disp/atr*2 = 0.25-0.41` and `rng/atr*1.5 = 0.93`. Total strength = 1.18-1.34 — below the 2.0 threshold. **Result: zero standalone OB detections across all stocks.**

**Impact**: Only LuxAlgo OB (tied to CHOCH/BOS events, `detect_ob_luxalgo`) produces OB signals. This means OB signals are sparse (only at structure break points) and miss many valid standalone OB zones.

**Fix direction**: Lower `min_strength` to 1.0 for A-share daily, or use a different normalization (e.g., `disp/rng` ratio instead of `disp/atr`).

## Root Cause 2: CHOCH/BOS utilization only 50-64% — `crossed` flag is one-and-done

**Location**: `signals_v19.py` lines 134-188

**Code**: `sh.crossed = True` at line 162 — once a swing is crossed, it's PERMANENTLY marked and never reused.

**Why it fails**: 
- `trend_bias` at line 153 determines CHOCH vs BOS at crossing time. If the first cross happens during a continuation (trend_bias==1 → BOS_Bull), the swing gets crossed. Later, if the trend reverses, the same swing should trigger CHOCH — but it's already crossed.
- 39-50% of swings never have their close cross the pivot price (lines 152, 174) — close must be strictly `>` (bull) or `<` (bear) relative to pivot.

**Impact**: 
- 600519: 18 swings but only 11 CHOCH+BOS (7 uncrossed swings)
- The remaining swings may be valid structure points that just never triggered the exact crossover condition in a 300-bar window

**Fix direction**: Reset `crossed` flag when `trend_bias` changes sign, or remove the flag entirely and use a different dedup mechanism (e.g., last 20 bars).

## Root Cause 3: Sweep nearly absent — requires pierce + close reversal + 30-bar swing window

**Location**: `signals_v19.py` lines 352-383

**Code**:
```python
min_pen = max(_calc_atr(ohlcv,14)*0.15, avg_price*0.001)
for sh_idx, sh_price in swing_highs:
    if sh_idx >= i-30 and sh_idx < i and bar['h'] > sh_price + min_pen:
        if bar['c'] < sh_price:  # Must close BELOW after piercing above
```

**Why it fails**:
- Average swing density: 1 swing per ~17 bars (300/18). With 30-bar window, each bar has ~1.8 candidate swings to check.
- The close reversal condition (`bar['c'] < sh_price`) is strict — many bars that pierce a swing high end up closing above it (strong momentum) or at it.
- 000858 has 8 pierce opportunities but only 3 close reversals (5 pierced-only, missed).

**Impact**: 3 of 7 stocks have ZERO sweeps. 000858 has the most (3) due to higher volatility.

**Fix direction**: Relax close reversal to `bar['c'] < sh_price * 1.002` (allow 0.2% tolerance), or detect sweeps on the bar AFTER the pierce (the reversal bar).

## Root Cause 4: EQL/EQH almost zero — adjacent-only pivot comparison with fixed 0.5% threshold

**Location**: `signals_v19.py` lines 433-456

**Code**:
```python
threshold = avg_price * 0.005  # 0.5% of average price
for i in range(1, len(highs)):
    prev, curr = highs[i-1], highs[i]
    if abs(curr.price - prev.price) <= threshold:
```

**Why it fails**:
- Only compares ADJACENT pivot pairs (i vs i-1). If two equal highs are 3 pivots apart (with a lower high in between), missed.
- 0.5% threshold: 茅台 at 1426 avg → 7.13 yuan (reasonable). 平安银行 at 11.2 → 0.056 yuan (very strict, essentially requiring EXACT equality).
- With only 4-9 highs per stock, there are only 3-8 adjacent pairs to compare.

**Impact**: Most stocks have 0-1 EQL/EQH. This is a detection algorithm limitation, not necessarily a market reality — stocks DO form equal highs/lows but the detection is too narrow.

**Fix direction**: Compare ALL pairs within a rolling window (e.g., last 5 pivots), not just adjacent. Use ATR-based threshold for low-price stocks.

## Root Cause 5: MSS sparse — reuses same swings as CHOCH/BOS with 12-bar cooldown

**Location**: `signals_v19.py` lines 389-427

**Code**:
```python
if i - last_mss < 12: continue  # line 404
for sh_idx, sh_price in highs:
    if sh_idx < i-3 and sh_idx >= i-40:  # line 410
```

**Why it fails**:
- Same swing points as CHOCH/BOS (already sparse: 8-18 per stock)
- 12-bar cooldown limits MSS to max ~25 over 300 bars
- 40-bar window further filters: swings older than 40 bars can't trigger MSS
- Despite these limits, actual MSS count is only 1-5 — meaning most bars pass through swing levels without triggering the crossover condition

**Impact**: MSS is too rare to form meaningful sequences with other signals. It's essentially decorative.

## Root Cause 6: Sequence windows are fixed, not adaptive to volatility

**Location**: `signals_v19.py` lines 583-604 (SEQUENCE_PATTERNS) and 606-638 (detect_signal_sequences)

**Code**: All patterns use fixed bar gaps [2,3,4,5]:
```python
{'name': 'Sweep→CHOCH→FVG→OB', 'types': [...], 'bars': [3,4,4]}
```

**Why it fails**:
- 宁德 (ATR=4.26%): high vol, price moves fast. A Sweep→CHOCH gap of 3 bars may be too LONG — the signals happen quickly.
- 招行 (ATR=1.23%): low vol, price moves slow. A 3-bar gap may be too SHORT — signals are spaced further apart.
- Fixed windows don't account for different stock "rhythms."

**Impact**: Only 1 sequence found for 600519 (64 signals), 2 for 000858 (62 signals). 3343/4800 stocks have zero sequences.

**Fix direction**: Scale bar gaps by `1/ATR_pct` — high-vol stocks get shorter windows, low-vol stocks get longer windows.

## Root Cause 7: Frontend renders non-area signals as bare horizontal lines

**Location**: `smc_unified.py` lines 89-98

**Code**:
```python
if t in ('Sweep_BSL','Sweep_SSL','CHOCH_Bull','CHOCH_Bear','BOS_Bull','BOS_Bear','MSS_Bull','MSS_Bear','EQL','EQH'):
    sig_lines.append({'yAxis':p,'lineStyle':{...},'label':{'show':True,...}})
```

**What's rendered**:
- markArea (colored rectangles): FVG_Bull, FVG_Bear, OB_Bull, OB_Bear, BPR ✅
- markLine (horizontal dashed lines): CHOCH, BOS, Sweep, MSS, EQL, EQH ⚠️

**What's MISSING from K-line chart**:
- Swing point markers (HH/HL/LL/LH labels on price chart)
- CHOCH/BOS "from→to" arrows (which swing was broken, where did it break)
- Multi-timeframe signal overlay (60min signals on daily chart)
- Signal sequence visualization (connect related signals with lines/arrows)
- Sweep "pierce+reversal" visualization (show the wick piercing the swing level)

**Impact**: The 13 signal types are all detected, but only 4 (FVG_Bull/Bear, OB_Bull/Bear) are clearly visible. The other 9 types appear as thin dashed lines that are hard to interpret without structural context.

## Sequence Filter Backtest Results

Comparison run on all 4800 stocks (script: `/root/.hermes/scripts/v11/seq_comparison.py`):

| Metric | Baseline (no filter) | Sequence (only) | Change |
|--------|---------------------|-----------------|--------|
| Active stocks | 1,360 | 332 | -76% |
| Total trades | 5,136 | 393 | -92% |
| WR | 70.8% | **74.6%** | +3.8pp |
| Avg PnL | +2.05% | **+2.28%** | +11% |
| Stocks with 0 sequences | — | 3,343 | 70% |

Direction: sequence filtering improves quality (WR +3.8pp, PnL +11%) but kills quantity (92% fewer trades).

Data: `/root/.hermes/smc_opt_v19/v19_seq_comparison.json`
