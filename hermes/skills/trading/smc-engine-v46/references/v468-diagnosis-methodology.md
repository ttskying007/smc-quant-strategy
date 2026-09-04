# V468 8-Bug Systematic Diagnosis Methodology

## When to Use

When a backtest/SMC engine produces results that seem off (unexpectedly high RR, 100% hold=1, TP never hit, price anomalies), use this methodology to systematically identify ALL root causes before attempting fixes.

## Step 1: Data Integrity Check

Always compare stored results against fresh runs before trusting any metrics.

```python
for trade in stored_trades[:10]:
    ohlcv = load_60m(trade_symbol)
    bar = ohlcv[trade['entry_idx']]
    ratio = trade['entry_price'] / bar['c']
    if ratio < 0.1 or ratio > 2.0:
        print(f"CORRUPTED: entry={trade['entry_price']} vs C={bar['c']} ratio={ratio}")
```

**Bug found this way**: V467 stored data had 32% corrupted prices (cache refresh between runs).

## Step 2: Trace Individual Trade Lifecycle

For any anomalous trade, trace through the EXACT engine logic:

```python
# Fresh backtest → get one trade result
# Then trace bar-by-bar:
for j in range(entry_idx+1, min(entry_idx+10, n)):
    bar = ohlcv[j]
    gain = (bar['h'] - entry_price) / entry_price * 100
    sl_hit = bar['l'] <= sl
    tp_prox = extreme >= tp_price * 0.90
    print(f"bar[{j}]: gain={gain:.2f}% sl_check={sl_hit} tp_prox={tp_prox}")
```

**Bug found this way**: TP proximity triggered at bar 43 (first bar after entry) because tp*0.90 was below entry price.

## Step 3: Check All Entry Price Computations

For every trade, verify the entry price against the OHLCV bar:

```python
entry_ratio = entry_price / entry_bar_close
# should be 0.99-1.01 for zone entry, exactly 1.0 for close entry
```

**Bug found this way**: ENTRY_AT_ZONE used `max(lower, close * 0.995)` creating systematic 0.5% discount that never filled.

## Step 4: Check All "Decoration" Code

Search for unpacked return values from decision functions:

```python
grep '_, _, _, _ = check_poi' *.py  # POI result discarded
```

Any function whose return values are unpacked to `_` is NOT doing its job — it's purely decorative.

**Bug found this way**: POI activation was checked but results (entry_price, sl) were never used. Trade fires regardless of whether price retraced.

## Step 5: Scale-Check All Thresholds Against Timeframe

For each threshold value, ask: "What percentage of ATR is this?"

| Threshold | Daily (ATR=0.5%) | 60min (ATR=2.5%) |
|:----------|:----------------:|:-----------------:|
| min SL 0.15% | 30% of ATR ✓ | 6% of ATR ✗ |
| BE at 0.2% | 40% of ATR ✓ | 8% of ATR ✗ |
| BE at 2.0% | 400% of ATR ✗ | 80% of ATR ✓ |

Rule of thumb for 60min trailing thresholds: 3-5x wider than daily (not 2x).

**Bug found this way**: All trailing thresholds were calibrated for daily data (ATR 0.3-1.0%), 60min ATR=1.5-3.7% needed 5-10x wider values.

## Step 6: Exit Path Audit

For each trade, determine the exact exit mechanism:

```python
for t in all_trades:
    if t['hold_bars'] <= 3:
        # Check: was exit via SL hit, trailing lock, TP proximity, or progressive BE?
        pass
```

**Bug found this way**: 100% of exits were via trailing, 0% via TP hit. This revealed the "fictitious TP" problem — TP targets are calculated but never reached because trailing exits first.

## Step 7: Check Swing Detection

For 60min data, verify the swing offset:

```python
swing = find_swing_high_forward(ohlcv, entry_idx, 200)
nearest_distance = swing['idx'] - entry_idx
# If nearest_distance > hold_bars, the TP is unreachable by definition
```

**Bug found this way**: skip=8 meant nearest swing was at bar+8+, but 69% of trades exited at hold=1. Impossible to ever reach TP.

## Step 8: Aggregate Verification

Cross-check aggregated results:

```python
# Sum of per-stock n_trades should equal total trade count
sum_stock = sum(s['n_trades'] for s in stock_results)
assert sum_stock == len(all_trades), f"Mismatch: {sum_stock} vs {len(all_trades)}"

# Check no negative hold_bars
assert all(t['hold_bars'] >= 0 for t in all_trades)

# Check entry_price coherence
for t in all_trades:
    assert 0.1 < t['entry_price'] < 10000, f"Bad entry: {t['entry_price']}"
```

## Full 8-Bug Catalog (this session)

| # | Bug | Found In | Root Cause | Fix |
|:-:|:----|:--------:|:-----------|:----|
| 1 | Entry price corruption | V467 stored data | Cache refresh between runs | Re-run full scan |
| 2 | Swing TP unreachable | V465-60min | skip=8, 69% hold=1 | skip=8→3 |
| 3 | Entry price fake 0.5% discount | V465-V467 | `close * 0.995` | Remove discount, use honest zone pricing |
| 4 | TP proximity premature | V467 | `extreme >= tp*0.90` fires at bar 1 | Add minimum gain gate `max(tp*0.90, entry*1.02)` |
| 5 | POI decorative | V465-V467 | Return values unpacked to `_` | Scan forward for real retrace (V468) |
| 6 | Trailing too tight for 60min | V465-V467 | Daily-scale thresholds on 60min data | 5-10x wider (8% BE/12% lock2%) |
| 7 | SL min too tight for 60min | V465-V467 | min=0.15% for all timeframes | min=0.30%, range 0.15-3.0% |
| 8 | "Weak reversal" OB noise | V467 | `weak_rev_+0%` with 0 Sweep/CHOCH | More aggressive filtering |

This methodology was developed iteratively during the V468 debugging session and saved as a reference so future agents can reproduce it efficiently.
