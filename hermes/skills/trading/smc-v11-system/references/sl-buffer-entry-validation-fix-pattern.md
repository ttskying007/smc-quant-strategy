# SMC SL Buffer + Entry Validation Fix Pattern

## The Problem: SL At Zone Low

V59-derived engines (daily_scan.py, full_scan.py, engine_v26.py) all compute SL directly at zone_low:

```python
# BROKEN:
sl_price = zone_lo - atr * params['sl_atr_mult']
# If atr is small, sl_price can be == zone_lo exactly
```

In V66 audit: 45/137 trades (33%) had `sl == zone_low` to within 0.001 — every intraday wick that touched zone_low triggered SL_HIT. Real-world result: disproportionate SL_HIT rate.

## The Fix: Hard Floor With Buffer

### In `daily_scan.py` (compute_sltp)

```python
def compute_sltp(pick, klines):
    dz_low = pick.get('dz_low', entry_price * 0.95)
    a = atr(klines, entry_idx)
    ap = a / entry_price * 100 if entry_price > 0 else 0

    sl_base = dz_low - a * params['sl_atr_mult']
    sl_pct_raw = abs(entry_price - sl_base) / entry_price * 100
    MIN_SL = max(ap * 0.5, 1.5)

    # NEW: Hard floor — SL must be below zone_low by at least 0.5%
    hard_floor_sl = dz_low * 0.995

    if sl_pct_raw < MIN_SL:
        sl_price = max(entry_price * (1 - MIN_SL/100), hard_floor_sl)
    else:
        sl_price = max(sl_base, hard_floor_sl)

    # Belt-and-suspenders: final check
    if sl_price >= dz_low:
        sl_price = dz_low * 0.995

    sl_pct = abs(entry_price - sl_price) / entry_price * 100
```

### In `full_scan.py` and `engine_v26.py`

Identical hard floor injection:

```python
# ── SL: zone_bottom - ATR × sl_mult ──
sl_price = zone_lo - atr * params['sl_atr_mult']

# Phase 0 Fix: Hard floor SL must be below zone_low by at least 0.5%
hard_floor_sl = zone_lo * 0.995
sl_price = max(sl_price, hard_floor_sl)

# Final check: ensure SL is below zone_low
if sl_price >= zone_lo:
    sl_price = zone_lo * 0.995

sl_pct = abs(entry_price - sl_price) / entry_price * 100
```

## Entry Above Zone Validation

In `daily_scan.py` scan_last_bars:

```python
entry_price = float(klines[entry_idx].get('o') or klines[entry_idx].get('c') or 0)
dz_low = float(z.get('low') or entry_price * 0.97)
dz_high = float(z.get('high') or entry_price)

# Phase 0 Fix: Reject entry above zone (max 0.8% tolerance)
entry_above_zone_pct = (entry_price / dz_high - 1) * 100 if dz_high > 0 else 0
if entry_above_zone_pct > 0.8:
    continue  # Price already broke through zone, no retrace happened

# Entry position validation: reject if price >3% below zone_low
if entry_price < dz_low * 0.97:
    continue  # Zone invalidated, entry too far below
```

## Calibrating the Thresholds

- `0.8%` above zone: too strict → rejects winning breakout trades (V66 audit showed 20 rejects, 3 were SL_HIT losers, 17 were winners)
- `0.5%` SL buffer: good balance — gives intraday wicks room without making SL too wide
- `3%` below zone: generous — zone should be invalidated if price drops this far below

Tuning guide from V66 audit:
- If rejecting too many winners at entry: raise 0.8% to 1.5%
- If SL_HIT still happens: increase SL buffer from 0.5% to 1.0%
- If zone invalidations are rare: the 3% threshold is fine

## Files to Patch

When applying this fix, ALWAYS patch all three files:
1. `/root/.hermes/scripts/v25/daily_scan.py` (compute_sltp + scan_last_bars entry validation)
2. `/root/.hermes/scripts/v25/full_scan.py` (SL hard floor + entry validation)
3. `/root/.hermes/scripts/v25/engine_v26.py` (SL hard floor)

Then verify all three compile: `python3 -m py_compile daily_scan.py full_scan.py engine_v26.py`

## Verification

After applying, run on V66 historical trades to verify:
```python
sl_below = sum(1 for t in trades if t['new_sl'] < t['zone_low'])
print(f"SL below zone: {sl_below}/{len(trades)} (should be 100%)")
```

Expected: goes from 33% (original V66) to **100%**.

## Related

- See `v66-iteration-audit-methodology.md` for the full audit protocol that identifies when this fix is needed
- See `/root/.hermes/smc_audit/v66_phase0_phase1_execution_report.md` for the execution results
