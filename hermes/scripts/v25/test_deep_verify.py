#!/usr/bin/env python3
"""Deep verification on 000858.SZ (五粮液) - a known active stock."""
import json, sys
sys.path.insert(0, '/root/.hermes/scripts/v25')
from pathlib import Path
from smc_core_pine_like import detect_all_signals_pine_like

fp = Path('/root/.hermes/kline_cache/000858_SZ_daily_300.json')
data = json.loads(fp.read_bytes())
print(f'Loaded {len(data)} bars for 000858.SZ')

res = detect_all_signals_pine_like(data)
sig = res['signals']

# Print all OB events with full detail
print('\n=== ALL OB SIGNALS ===')
for ob in sig.get('obs', []):
    print(f'  bar={ob["index"]:3d} dir={ob["direction"]:4s} zl={ob["zone_low"]:.2f} zh={ob["zone_high"]:.2f} '
          f'disp={ob.get("displacement_ratio","N/A")}x conf={ob["confidence"]} '
          f'src={ob.get("source_event","?")} confirm={ob.get("confirm_index","?")}')

# Print structure events
print('\n=== ALL STRUCTURE EVENTS (CHOCH/BOS) ===')
for ev in sig.get('structure', []):
    mss = 'MSS' if ev.get('is_mss') else '   '
    print(f'  bar={ev["index"]:3d} type={ev["type"]:5s} dir={ev["direction"]:4s} '
          f'price={ev["price"]:.2f} level={ev.get("source_level","?")} {mss}')

# Print sweeps
print('\n=== ALL SWEEPS ===')
for sw in sig.get('sweeps', []):
    print(f'  bar={sw["index"]:3d} sub={sw.get("subtype","?"):3s} dir={sw["direction"]:4s} '
          f'price={sw["price"]:.2f} pool={sw.get("pool","?")}')

# Print FVGs
print(f'\n=== FVGs: {len(sig.get("fvgs",[]))} total ===')
for fv in sig.get('fvgs', [])[:10]:
    print(f'  bar={fv["index"]:3d} dir={fv["direction"]:4s} gap_low={fv["gap_low"]:.2f} gap_high={fv["gap_high"]:.2f}')
if len(sig.get('fvgs',[])) > 10:
    print(f'  ... and {len(sig.get("fvgs",[])) - 10} more')
