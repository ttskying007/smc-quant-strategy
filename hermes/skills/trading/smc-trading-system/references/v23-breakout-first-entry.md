# V23 Breakout-First Entry Architecture

## The Correction That Drove V23

User: "入场点还是不对，突破后的回踩兴趣点"

Translation: "Entry point still wrong. Pullback to POI after breakout."

This revealed that V21/V22's "zone retrace" model was architecturally incomplete — they entered at ANY retrace to a demand zone without first requiring a Break of Structure (BOS/CHOCH). In real SMC, the sequence is:

1. Demand zone forms (OB/FVG)
2. Price breaks out above (BOS/CHOCH) — confirms structure shift
3. Price retraces to test the zone (POI = Point of Interest)
4. Confirmation at the zone (IDM/PB)
5. Entry

Without step 2 (breakout), you're entering on random pullbacks, not on structural retests.

## Engine Location
`/tmp/v23_engine.py` — 543 lines, self-contained

## Key Design Decisions

### 1. BOS Must Precede Retrace (Strict)
```python
search_start = bos_idx + 1         # BOS after zone
search_end = min(bos_idx + 25, n-2) # 25-bar window
```
BOS must occur above the zone, and retrace MUST happen after BOS. No exceptions.

### 2. Wick Penetration for Retrace Detection
```python
if lows[i] < dz_low * 0.995:  # price pierces zone
```
Using LOWS not CLOSES — captures wick penetrations that closes would miss.

### 3. Two Confirmation Types Only
- IDM_BOUNCE: wick_low > body × 1.5, close > zone_low
- PB_BOUNCE: wick_low > body × 2, close > zone_low, close > prev_close
- REV_BOUNCE: DELETED (too weak — any bullish candle counted)

### 4. Gap Protection
```python
if entry_price > dz_low * (1 + MAX_GAP_PCT/100): continue
```
Next-day open must not gap >3% above zone. Prevents entry at inflated prices.

### 5. Structural SL (100% Coverage)
Finds pre-entry structures in priority: swing_low > OB_lower > FVG_lower
Requires 2% ≤ distance ≤ 8% from entry.

### 6. Structural TP (Multi-Tier)
Finds post-entry resistance: swing_high > OB_upper > FVG_upper > BOS_level
Requires ≥1% above entry. Deduplicates by price proximity (±0.5%).

## Window Size Tradeoff (12 vs 25 bars)

| Window | Trades | WR | Lesson |
|--------|--------|-----|--------|
| ±15 from BOS | 3459 | 79.3% | Pre-BOS retraces included — user rejected |
| +1~+12 | 785 | 56.8% | Too narrow, missed valid post-breakout retraces |
| +1~+25 | 1609 | 58.0% | Current balance — WR still needs improvement |

The 12→25 bar window widened trades 2x but WR barely moved. Suggests BOS quality filtering (breakout magnitude, ctx_score) matters more than retrace timing.

## V23 Results Summary
- 1609 trades / 1202 stocks / WR=58.0% / avgPnL=+2.07%
- avgWin=+6.31%, avgLoss=-3.79%, RR=1.66x
- TP1 hit rate: 57.5%
- 100% structural SL + multi-tier structural TP (avg 5.7 tiers/trade)
- Exit distribution: SL_hit=41.8%, TP_FVG=32.8%, TP_OB=12.2%, TP_swing=7.2%, TP_BOS=5.3%

## Future Improvement Directions
1. BOS quality filter: require breakout magnitude ≥ ATR × 0.5
2. POI quality: score demand zones by ctx_score, filter weak zones
3. Consecutive BOS rejection: skip if multiple BOS within 10 bars
4. Dynamic retrace window: widen for HV regimes, tighten for ST
