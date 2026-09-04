# Zone Field Naming Convention Defect (V59→V64→V65→V66 Pipeline)

## Observation

V66/V65 trades JSON files have `raw_zone_low/raw_zone_high` populated (e.g., 3.38, 3.59) but `zone_low/zone_high` are `None`. The same for `tp1_design_price_v59` (populated) vs `tp1` (None).

## Root Cause

The V59 full-market scanner writes zone boundaries under `raw_zone_low`/`raw_zone_high` and TP prices under `tp1_design_price_v59`/`tp2_design_price_v59`. The canonical field contract expects `zone_low`, `zone_high`, `tp1`, `tp2`.

V65 engine (`v65_engine.py`) uses `nt = dict(t)` to copy all V64 source fields, but does NOT map `raw_zone_low → zone_low`. Same for V66. The field contract normalizer `_apply_smc_field_contract()` in `smc_unified.py` already contains a fallback chain:
```python
r['zone_low'] = _float_or_zero(r.get('zone_low') or r.get('execution_zone_low') or r.get('raw_zone_low') or r.get('dz_low') or r.get('lower'))
```
This works at the API/frontend layer but does NOT fix the physical JSON on disk.

## Impact

- Direct readers of `v66_trades.json` see `zone_low=None` (no zone boundaries).
- `entry_zone_position` cannot be computed (needs zone_low + zone_high).
- Trades and picks served by API/frontend ARE correct because `_apply_smc_field_contract` runs per-request. But file-level integrity is broken.

## Fix Applied (2026-06-10)

1. **`smc_unified.py` `_apply_smc_field_contract`**: added `entry_zone_position` calculation, `tp1 ← tp1_design_price_v59/v56/v55`, `tp2 ← tp2_design_price_v59/v56/v55`.
2. **`v65_engine.py`**: after `nt = dict(t)`, add `zone_low ← raw_zone_low`, `zone_high ← raw_zone_high`, `tp1 ← tp1_design_price_v59`, `tp2 ← tp1_design_price_v59`, compute `entry_zone_position`.
3. **`v66_engine.py`**: same fix.
4. **JSON backfill**: all version JSON files (V64 source, V65, V66, V71, V72) backfilled with zone_low/zone_high/tp1/tp2/entry_zone_position from raw_zone_*/tp1_design_price_* fields.

## Required for Future Engine Iterations

Any engine that copies/transforms trades must canonicalize field names at write time. Do not rely on `_apply_smc_field_contract` as a per-request runtime fix — it only applies at API layer, not file layer.

Normalization checklist at engine output:
- `zone_low ← raw_zone_low` (if zone_low missing)
- `zone_high ← raw_zone_high` (if zone_high missing)
- `tp1 ← tp1_design_price_v59/v56/v55`
- `tp2 ← tp2_design_price_v59/v56/v55`
- `entry_zone_position ← (entry_price - zone_low) / (zone_high - zone_low)` (if both available)
