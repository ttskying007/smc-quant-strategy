# Monitor TP/SL Bar Walk Fix (2026-05-14)

## Bug
Monitor `check_exits()` only checked the LAST daily bar's high/low for TP/SL triggers.
This missed intermediate bar hits where TP/SL was triggered on a bar that was no longer the latest.

Example: 002289_SZ hit TP at bar=299 (h=48.98 ≥ TP=48.07), but monitor only saw bar=300 (h=46.83 < TP).

## Fix
Replace single-bar check with full bar-by-bar walk-forward:
- Find entry bar in daily OHLCV cache
- Walk forward from entry_bar+1 to last bar
- Check each bar: TP first (favorable), then SL
- Record first hit with exit date and PnL

## Code Location
`/root/.hermes/scripts/v11/monitor_check.py` — `check_exits()` function

## Impact
- 002289_SZ correctly detected as TP hit (was showing as "open")
- 301188_SZ correctly detected as SL (was showing as TP — wrong bar order)
- WR changed from 79.4% to 77.1% (more accurate)
