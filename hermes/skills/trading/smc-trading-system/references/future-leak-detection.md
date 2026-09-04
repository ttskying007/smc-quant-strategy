# Future Leak Detection in SMC Backtesting

## Detection Heuristic

When user says "回测不对" or WR looks implausibly high:

1. **Check zone-type distribution** — if a single zone type dominates (>50%), audit its signal generation code for forward scanning.
2. **OTE dominance >50% is a red flag** — OTE requires impulse leg computation. If it looks too far into the future, it's leaking.
3. **WR drops >10pp after removing a zone type** — confirms that zone type was inflated by future data.

## V27 OTE Leak (2026-05-19)

**Symptom**: OTE zones = 56% of all zones, raw WR = 67.2%.

**Root cause**: `ote_signals()` scanned 15 future bars to find impulse extreme:

```python
# LEAK — scans future bars
end_price = float(klines[ev_idx].get('h', 0))
for j in range(ev_idx, min(ev_idx + 15, n)):
    end_price = max(end_price, float(klines[j].get('h', 0)))
```

**Impact**: OTE zone placed higher than knowable at event time → price "retraces" into artificially favorable zone → inflates WR by ~12pp.

**Fix**: Use only the event bar itself as impulse end:
```python
end_price = float(klines[ev_idx].get('h', 0))
```

**Post-fix**: OTE dropped to 33% of zones, OB became dominant (67%), raw WR dropped to honest 54.7%.

## Audit Methodology

For each signal type, trace time-axis:

| Signal | Data window | Future leak risk |
|--------|------------|-----------------|
| confirmed_swings | confirm_idx = pivot_idx + RIGHT | No — used only at confirm_idx |
| BOS/CHOCH/MSS | break bar uses only confirmed swings | No |
| OB | backward scan from event | No |
| OTE | impulse_end MUST NOT scan forward | **High** — audit this |
| BPR | FVG overlap | No (FVG is 3-bar confirmed) |
| PO3 | sweep before event, event after | No |
| SWEEP | single-bar pierce+reclaim | No |

## Verification

After any signal code change, run on 200+ stocks and compare:
- Zone type distribution (should be OB > OTE, not the reverse)
- Raw WR (should not spike >10pp from prior run)
- Per-stock trade count (should not drop to 0 for many stocks)
