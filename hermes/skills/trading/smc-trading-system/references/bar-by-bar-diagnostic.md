# Signal Accuracy Verification: Bar-by-Bar Diagnostic Method

## When to Use

When SMC signals appear inaccurate — wrong position, over-detection, under-detection, or duplicate triggering.

## Method

1. Pick a representative stock (e.g., 600519.SH for high-price, 301137.SZ for volatile)
2. Print every single bar (0-N) with full OHLC data
3. Annotate swing points with type and label (HH/HL/LH/LL)
4. Mark every detected signal with type, zone range, strength
5. Visually verify each signal against standard SMC definitions

## Diagnostic Script Template

```python
for i in range(n):
    b = ohlcv[i]
    d = str(b.get('t', ''))[:10]
    sigs_here = sig_by_bar.get(i, [])
    
    line = f"[{i:3d}] {d} O={b['o']:>8.2f} H={b['h']:>8.2f} L={b['l']:>8.2f} C={b['c']:>8.2f}"
    
    for sw in swings:
        if sw.bar_idx == i:
            line += f"  ◄ {sw.type}{{{sw.label}}}@{sw.price:.2f}"
    
    if sigs_here:
        for s in sigs_here:
            line += f"\n       → {s.type} dir={s.direction} str={s.strength:.1f}"
    
    print(line)
```

## Common Bugs Found via This Method

### V20→V21 Fixes:
1. **BOS/CHOCH over-triggering**: Multiple signals at same structural break event (bars 78-80 for same break)
2. **Sweep duplication**: Same liquidity sweep detected 4-6 times (bars 203, 205, 206, 217)
3. **EQL type mismatch**: Signal type 'EQL'/'EQH' doesn't match SIG_STYLE 'EQL_High'/'EQL_Low'

### V21→V22 Fixes:
1. **OB range bug**: Searching from sw_bar→break_bar (forward) instead of backward from break_bar
2. **Missing signals**: IFVG, Breaker Block, LV, RB, OTE, PO3 not implemented
3. **Swing detection**: Simplified static window missed most swings — restored LuxAlgo leg() state machine

## Verification Checklist

For each signal type, verify:
- [ ] Position: is the signal at the RIGHT bar (not offset)?
- [ ] Price: does the signal price match the structural level?
- [ ] Duplicates: is the same event detected multiple times?
- [ ] Missing: are there clear signals that should have been detected but weren't?
- [ ] Context: does the signal make sense in the broader trend context?
