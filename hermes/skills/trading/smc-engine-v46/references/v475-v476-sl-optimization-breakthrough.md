# V475/V476 — SL Optimization Breakthrough (2026-05-12)

## Context

User Lei asked to analyze why RR was insufficient across all V13→V467 engine versions. The answer was not in signal detection, not in trailing logic, not in TP calculation — it was in **SL priority**.

## Root Cause: SL Type RR Degradation

### Before V475 (V467)

The original engine's `calc_v45_sl()` had a 3-step priority:

1. **Signal boundary SL** (checked first): If OB lower is 0.08%-1.5% from entry, use it → `ob_lower`
2. **Swing point SL** (checked second): If nearest swing low is 0.10%-2.0% from entry, use it → `swing_low`
3. **ATR adaptive SL** (fallback): Fixed at 0.15-0.3% → `adaptive`

Result for V467 (1472 trades):
- adaptive (50.6%): SL=0.19%, RR=21.33x
- ob_lower (39.3%): SL=0.56%, RR=8.41x
- swing_low (10.1%): SL=0.68%, RR=7.19x

The problem: step 1 and 2 **always fire when their conditions are met**, even if the adaptive SL is much tighter. All 3 SL types had 100% WR because the trailing lock never let SL trigger. The wide SL was pure waste — it only made the RR denominator bigger without any protection benefit.

### Fix: Skip Signal Boundary + Swing Point SL

**V475**: Remove OB boundary check (keep FVG boundary — FVG depends on zone price)
**V476**: Remove swing point check too — 100% ATR-adaptive

After fix: ALL trades use SL=0.15-0.30% (ATR-based). 1-bar RR jumped 33%.

## Verification Methodology

### Step 1: Data analysis
- Loaded V467 full trades, calculated RR distribution, SL type breakdown, hold distribution
- Found: RR is linearly correlated with SL size, not with any other factor
- Key stat: adaptive median SL=0.19% vs ob_lower median SL=0.56%

### Step 2: 200-stock side-by-side
- Created `_run_variant.py` — monkey-patches the engine's `calc_v45_sl` function
- Ran 3 variants: adaptive-only, adaptive+tighter BE, adaptive+higher MIN_RR
- All 3 identical on 200 stocks: RR jumped from ~14x to ~26x

### Step 3: Full 4552 scan
- Created `v475_engine.py` and `v476_engine.py` from `v467_engine.py` copies
- Modified only `calc_v45_sl()` — removed OB boundary check (V475) and swing point check (V476)
- Changed OUTPUT_DIR, saved as separate version
- Both passed full 4552 scan (~80s each)

## Key Numbers

| Metric | V467 | V475 | V476 |
|--------|------|------|------|
| Stocks | 630 | 659 | 894 (+42%) |
| Trades | 1472 | 1536 | 2124 (+44%) |
| WR | 82.7% | 83.0% | 86.3% (+3.6pp) |
| RR | 16.49x | 19.79x | **23.32x (+41%)** |
| PF | 194 | 122 | 206 |
| PnL/tr | +4.52% | +4.59% | +4.18% |

## SL Formula (V476)

```python
def calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction, params, all_signals):
    # 1. FVG boundary (keep — FVG depends on zone price structure)
    if direction == 'bull' and 'FVG' in signal.get('type',''):
        lower = signal.get('lower', 0)
        if lower > 0 and lower < entry_price:
            pct = (entry_price - lower) / entry_price * 100
            if 0.08 <= pct <= 1.5:
                return lower, 'fvg_lower', round(pct, 2)
    
    # 2. 100% ATR adaptive SL (skip all OB/swing boundaries)
    atr = calc_atr_v45(ohlcv, entry_idx)
    sl_mult = params.get('sl_mult', 0.3)
    base_sl = max(0.15, min(1.5, atr * sl_mult * 0.3))
    return round(entry_price * (1 - base_sl/100), 4), 'adaptive', round(base_sl, 2)
```

## Remaining Issues

1. **hold>=3 trades**: 185 trades (8.7%) hold 3+ bars, WR=44.6%, RR=1.09x. These are BE-locked stalls. Possible fix: tighter progressive BE `[(2,0.0),...]`.

2. **PnL slightly lower**: 4.18% vs 4.52%. V476 accepts more marginal trades. Trade count +44% offsets this.

3. **60min only**: Not validated on daily data. Adaptive SL may behave differently on daily.
