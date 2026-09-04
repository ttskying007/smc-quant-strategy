# V12 Hybrid Forward Bug — 2026-05-11 Diagnostic

## Bug: Line 398 Walrus Operator

```python
# signals_v12.py line 398
if swing_mode := 'hybrid':  # BUG: := assignment, always True
```

**Fix**: `if swing_mode == 'hybrid':`

The `:=` walrus operator assigns `'hybrid'` to `swing_mode`, and the expression `'hybrid'` is truthy. This block always executes regardless of any callers setting `swing_mode='swing_only'`.

## Impact

600997.SH 60min (200 bars):
- V12 OB_Bull = 23 total
- swing_backward_v2: 5 (22%) — correct positions from swing-scan
- hybrid_forward: 18 (78%) — wrong positions from per-candle forward scan (V11's original bug)

## Why Hybrid Forward Produces Wrong OBs

The hybrid forward scan iterates EVERY candle from 5 to n-3 (lines 407-504), exactly like V11's original `detect_ob_v11()`. For each bearish candle it:

1. Looks forward 15 bars for max price
2. Requires `displacement >= hybrid_disp_mult` (with displacement_mult=1.0, hybrid_disp_mult = max(0.8, 0.7) = 0.8 — very loose)
3. Requires a nearby swing point within 20 bars
4. Only requires `imp >= 1` (at least 1 bullish bar after)

With dis_ratio >= 0.8 and imp >= 1, almost any bearish candle with an uptrend nearby qualifies. These OBs are at random positions within the structure, NOT at the last opposite candle before impulse.

## 200-stock Consequence

V12 200-stock backtest: WR=17.5%, P&L=+1214% (high RR, low WR)

The high RR (winners win big) means a few correctly-positioned OBs produce large profits. The low WR (17.5%) means most entries are at wrong positions and lose. This matches the hybrid_forward dominance — 78% wrong positions, 22% correct.

## Secondary Issue: Swing-Backward Too Few

Even without the walrus bug, swing-backward finds only 5-6 OBs from 12 swing highs on this stock:

| Swing High | Result | Reason |
|------------|--------|--------|
| idx=23 | OB at 20 | OK (impulse=2) |
| idx=36 | SKIP | All dojis around swing, then BULL→doji→BULL pattern confuses phase tracking |
| idx=54 | SKIP | See above — multiple BULL bars at top get consumed into `impulse_len=1` |
| idx=71 | SKIP | Similar pattern — bearish is 2 bars below swing |
| idx=77 | SKIP | BULL→BEAR at top, phase='impulse'→bar is bearish→impulse_len=1→skip |
| idx=86 | OB at 82 | OK (impulse=3) |
| idx=91 | OB at 88 | OK (impulse=2) |
| idx=99 | SKIP | same |
| idx=147,159 | Mixed | 159 found but volume killed |
| idx=168 | SKIP | body=0.00% (doji) |
| idx=173 | OB at 169 | OK (impulse=3) |

The pattern: many swing highs have a long run of BULL bars immediately before the peak. The phase logic finds the first BULL bar and sets `impulse_len=1`, then as it scans backward and hits BULL→BULL→BULL, it keeps incrementing impulse_len. But when it finally hits a BEAR bar, impulse_len may already be >= 2 so the OB is found. The problem is when there's a BULL bar, then a doji or BEAR bar too close — the phase logic terminates prematurely.

## Fix Options

1. **Remove hybrid pass entirely** (lines 393-504). Only use swing-backward.
2. **Fix walrus operator**: change `:=` to `==`.
3. **Relax impulse_len filter**: allow `impulse_len >= 1` for 60min data (day data should keep >= 2).
4. **Improve doji handling**: doji bars should not break momentum — treat as continuation not termination.
5. **Increase swing count**: reduce `swing_right` from 3 to 2 for 60min to get more swings.

## Debug Scripts

- `_compare_signals.py`: Compare V12 vs V-Pine counts on a single stock
- `_debug_v12_swings.py`: Print backward scan from each swing high, showing why OBs are skipped
- `_debug_ob_scan.py`: Manually run V12 OB backward scan to count actual results
