# V15 Pine Script Alignment — Signal-by-Signal Comparison

2026-05-12. Three Pine Script references used:
- **LuxAlgo SMC** (50KB): Swing structure, OB (volatility-aware), EQH/EQL, FVG (MTF)
- **SMC 2026** (60KB): OB (swing-backward+displacement), CHOCH/BOS (trend state machine), FVG (pure gap), EQH/EQL (consecutive pivot)
- **Waves Ultimate** (4KB partial): pivothigh/pivotlow with right confirmation

Pine files at: `/root/.hermes/scripts/v11/pine_refs/`

---

## 1. SWING DETECTION

**Pine (SMC 2026):**
```pinescript
swing_high_ms = ta.pivothigh(high, 5, 5)  // left=5, right=5
last_swing_high_idx := bar_index - 5       // actual pivot was 5 bars ago
```

**Pine (Waves Ultimate):**
```pinescript
ta.pivothigh(highSrc, 5, 2)  // left=5, right=2
```

**V15:**
```python
detect_swings_v15(ohlcv, left=5, right=2)
# Checks: bar[i] is highest in [i-5, i+2]
# Returns: {'idx': i+2, 'bar_idx': i, 'price': high[i]}
# ATR filter: adjacent same-direction swings merged if amplitude < 0.3*ATR
```

**Alignment**: Exact. V15 matches Waves Ultimate params (left=5, right=2). Also produces internal swings (left=3,right=1) for MSS and EQL swings (left=4,right=2).

---

## 2. FVG (Fair Value Gap)

**Pine (SMC 2026):**
```pinescript
if low > high[2]  // bullish gap
    gapSize = low - high[2]
    if gapSize >= atr * 0.5  // fvg_atr_mult=0.5
```

**V14 (WRONG):**
```python
if b1['h'] < b3['l']:  # bar1 high < bar3 low
    if gap_pct >= min_width and (c2_body_ok or all_bearish):  # OR logic!
```

**V15:**
```python
# Pine exact: current bar (b0) low > 2-bars-ago (b2) high
if b0['l'] > b2['h']:
    gap = b0['l'] - b2['h']
    if gap >= atr_val * 0.5:
        # Quality: all 3 candles same direction
        all_bull = b0_bull and b1_bull and b2_bull
        grade = 3 if all_bull else 2
```

**Key differences V14→V15:**
1. Bar index: V14 used b1/b3 (wrong offset) → V15 uses b0/b2 (Pine exact)
2. Condition: V14 OR logic → V15 AND quality (all_same_dir adds grade)
3. ATR filter: V14 used `fvg_min_width` → V15 uses `atr * 0.5` (Pine exact)

---

## 3. OB (Order Block)

**Pine (SMC 2026 — Bull OB):**
```pinescript
swing_low_ob = ta.pivotlow(low, 7, 7)  // confirmed pivot, swing_length=7
if not na(swing_low_ob):
    for i = 8 to 17:  // scan backward 8-17 bars
        if close[i] < open[i]:  // bearish candle
            disp = swing_low_ob - low[i]    // distance from OB low to swing
            rng  = high[i] - low[i]         // OB candle range
            if disp > (rng * 1.5):          // displacement_filter
                // FOUND OB at bar_index - i
```

**V14 (CRITICAL BUG):**
```python
# Used `_quick_swing_highs(ohlcv, 8)` — NO RIGHT CONFIRMATION
# Every 8-bar local max treated as swing point
# Result: OB at random trend-internal positions
```

**V15:**
```python
# 1. Detect confirmed swings: pivothigh/pivotlow with left=7, right=2
swings = detect_swings_v15(ohlcv, left=7, right=2)

# 2. For each CONFIRMED swing low, scan backward
for sl in swing_lows:
    sl_bar = sl['bar_idx']   # actual pivot bar
    sl_price = sl['price']
    
    for back in range(sl_bar-1, sl_bar-15, -1):
        bar = ohlcv[back]
        if bar['c'] < bar['o']:  # bearish candle (OB candidate)
            rng = bar['h'] - bar['l']
            disp = sl_price - bar['l']   # distance from OB low to swing low
            if disp > (rng * 1.5):       # displacement filter
                # Verify impulse between OB and swing
                has_impulse = any(ohlcv[fwd]['c'] > ohlcv[fwd]['o'] 
                                  for fwd in range(back+1, sl_bar))
                if has_impulse:
                    # OB FOUND — correct position
```

**Key V14→V15 fix:**
- V14: `_quick_swing_*` (right=0) → finds OBs at every local wiggle
- V15: `detect_swings_v15(left=7,right=2)` → only at structural swing points
- Added impulse verification between OB and swing
- `at_structure: True` in all metadata (not sometimes False)

---

## 4. CHOCH / BOS (Structure)

**Pine (SMC 2026):**
```pinescript
var int swing_trend = 0  // 0=neutral, 1=bullish, -1=bearish

if close > last_swing_high and bar_index > last_structure_label_bar + 20:
    if swing_trend == -1: tag = "CHoCH"  // trend reversal
    else: tag = "BOS"                    // trend continuation
    swing_trend := 1

if close < last_swing_low and bar_index > last_structure_label_bar + 20:
    if swing_trend == 1: tag = "CHoCH"
    else: tag = "BOS"
    swing_trend := -1
```

**V15:**
```python
swing_trend = 0
last_label_bar = -999

for i in range(n):
    # Update last known swing levels as they become available
    ...
    if i - last_label_bar < 20:  # spacing constraint
        continue
    
    if bar['c'] > last_swing_high:
        tag = 'CHOCH_Bull' if swing_trend == -1 else 'BOS_Bull'
        swing_trend = 1
    
    elif bar['c'] < last_swing_low:
        tag = 'CHOCH_Bear' if swing_trend == 1 else 'BOS_Bear'
        swing_trend = -1
```

**Key V14→V15 fix:**
- V14: no trend tracking — every break treated as CHOCH
- V15: full state machine — correctly distinguishes BOS (continuation) from CHOCH (reversal)
- BOS is a NEW signal type in V15

---

## 5. MSS (Market Structure Shift)

**V15:** Uses internal (shorter) pivot points (left=3, right=1), min 8 bars spacing.

**Key V14→V15 fix:**
- V14: 3-bar window (`local_window=3`) → any micro move triggers MSS
- V15: internal pivot structure (left=3,right=1) → only meaningful structure breaks

---

## 6. SWEEP (Liquidity Grab)

**V15:** MUST break a recent (<15 bars) swing point AND close back inside (reversal).  
`bar['h'] > sh_price and bar['c'] < sh_price` for bearish sweep.

**Key V14→V15 fix:**
- V14: any candle with `upper_wick >= body * 2` triggered sweep — no swing point check
- V15: MUST break a recent swing point AND reverse

---

## 7. EQL / EQH (Equal Highs / Equal Lows)

**Pine (SMC 2026):**
```pinescript
ph = ta.pivothigh(4, 4)  // eqhl_pivot_length=4
if abs(ph - previousHigh) < atr * 0.1: // EQH!
```

**V15:** Consecutive pivot comparison — `abs(curr['price'] - prev['price']) < atr_val * 0.1`. Deduplication by level+direction.

**Key V14→V15 fix:**
- V14: price clustering (sort all swings by price, group by proximity) — time-agnostic, wrong
- V15: consecutive pivot comparison (Pine exact)

---

## 8. BPR (Balanced Price Range)

**V15:** (Bull FVG ∪ Bull OB) ∩ (Bear FVG ∪ Bear OB) overlap. Dedup by rounded (oh, ol) key.

**Key V14→V15 fix:**
- V14: only FVG_Bull ∩ FVG_Bear
- V15: multi-source overlap (FVG + OB zones)

---

## Parameters (SMC 2026 user defaults)

| Parameter | Value | Pine Source |
|-----------|-------|-------------|
| swing_left / swing_right | 5 / 2 | Waves Ultimate |
| ob_left / ob_right | 7 / 2 | SMC 2026 ob_swing_length=7 |
| ob_displacement_mult | 1.5 | SMC 2026 user setting |
| ob_lookback | 10 | SMC 2026 user setting |
| fvg_atr_mult | 0.5 | SMC 2026 user setting |
| eqhl_pivot_left / right | 4 / 2 | SMC 2026 eqhl_pivot_length=4 |
| eqhl_threshold | 0.1 | SMC 2026 default |
| internal_swing_left / right | 3 / 1 | LuxAlgo internal structure |
| structure_spacing | 20 bars | SMC 2026 |
| sweep_recent_limit | 15 bars | ICT standard |
