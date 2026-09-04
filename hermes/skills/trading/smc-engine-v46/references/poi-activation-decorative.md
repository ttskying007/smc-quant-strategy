# POI Activation is Decorative (Documented 2026-05-11)

## The Problem

In all V45/V465/V466/V467 engines (`evaluate_v45_entry()`), the POI activation check is **purely decorative**. It records whether the price happened to be inside the POI zone, but it does NOT control entry timing.

## Current Code (all engines)

```python
def evaluate_v45_entry(...):
    ...
    entry_bar = max(sig_idx, confirmed_at)  # ← ALWAYS immediately next bar
    
    ...
    # POI activation check — return values DISCARDED
    poi_activated, _, _, _ = check_poi_activation(ohlcv, sig, entry_bar, sig_dir)
    # The underscore unpacking means: entry_price, sl_price, sl_type are thrown away
    # Only the boolean 'poi_activated' is recorded as metadata
    
    ...
    # Entry price uses zone boundary, NOT POI retracement check
    entry_price = _calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)
```

The net effect: entry happens on `max(sig_idx, confirmed_at) + 0` regardless of whether price actually retraced to the signal's price zone.

## Why This Matters

For a corrective/reversal trade (OB at a swing low), the ideal entry is when price **RETURNS** to the OB zone after initially breaking out. The current code enters at the close of the next bar after signal detection — which may be at a much higher price if the stock gaps up on strong momentum.

On 60min data, 5/5 trades for 003003.SZ show the pattern: signal bar AND entry bar are both already inside the POI zone, so the check passes trivially. But on stocks where price gaps away from the zone, the entry fires anyway.

## Pattern Analysis (003003.SZ, all 5 trades)

```
Trade 0:
  Signal@bar[81]: O=12.43 H=12.47 L=12.26 C=12.28 (in zone 12.26-12.47)
  Entry@bar[82]:  O=12.32 H=12.42 L=12.19 C=12.41 (in zone)
  hold=1b — entered at bar+1, exited at bar+2

Trade 1-4: Same pattern — entry always at bar+1, always in zone because signal bar IS the zone
```

## The Fix

Replace the `entry_bar = max(sig_idx, confirmed_at)` with a POI-searching loop:

```python
# Search forward for POI retracement
entry_bar = None
for candidate in range(max(sig_idx, confirmed_at), min(sig_idx + 40, n)):
    activated, retest_price, sl_price, sl_type = check_poi_activation(
        ohlcv, sig, candidate, sig_dir)
    if activated:
        entry_bar = candidate
        # Override entry price and SL to POI-based values
        override_entry_price = retest_price
        override_sl = sl_price
        override_sl_type = sl_type
        break

if entry_bar is None:
    return None  # No POI retracement within window — skip trade
```

Key behavioral change:
- If the stock gaps up after OB detection and never retraces → trade is SKIPPED (correct)
- If the stock retraces to OB zone after 5 bars → trade fires at retest price (better entry)
- Only trades WITH a retracement enter (reduces trade count but increases entry quality)

## Expected Impact on 60min Performance

Expected from the 003003.SZ analysis:
- All 5 trades currently fire because price is in zone on bar+1 already
- No change for stocks where price never leaves the zone
- Stocks that gap away will skip poorly-timed trades (reducing volume but likely increasing WR)

## Related Skills

- smc-engine-v45: contains the engine code
- smc-core-concepts: POI zone theory
- smc-v11-system: signal detection that generates zone prices (lower/upper)
