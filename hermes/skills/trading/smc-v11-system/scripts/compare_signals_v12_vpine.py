#!/usr/bin/env python3
"""Diagnostic: Compare signal counts between V12 and V-Pine on one stock.

Usage:
  python3 _compare_signals.py [stock_symbol]

Example:
  python3 _compare_signals.py 600997_SH

Output: signal counts, first-N OB positions with metadata.
"""
import json, sys, os
sys.path.insert(0, '/root/.hermes/scripts')
os.chdir('/root/.hermes/scripts/v11')

from signals_v12 import detect_all_signals_v12, calc_adaptive_thresholds as calc_v12
import importlib.util, types

# Set up v11 package for signals_vPine's import
v11_pkg = types.ModuleType('v11')
v11_pkg.__path__ = ['/root/.hermes/scripts/v11']
sys.modules['v11'] = v11_pkg
spec_v11 = importlib.util.spec_from_file_location('signals_v11', '/root/.hermes/scripts/v11/signals_v11.py')
v11_mod = importlib.util.module_from_spec(spec_v11)
sys.modules['v11.signals_v11'] = v11_mod
spec_v11.loader.exec_module(v11_mod)

spec_vp = importlib.util.spec_from_file_location('signals_vPine', '/root/.hermes/scripts/v11/signals_vPine.py')
vp_mod = importlib.util.module_from_spec(spec_vp)
sys.modules['signals_vPine'] = vp_mod
spec_vp.loader.exec_module(vp_mod)

symbol = sys.argv[1] if len(sys.argv) > 1 else '600997_SH'
cache_file = f'/root/.hermes/kline_cache_60min/{symbol}_60min_200.json'
with open(cache_file) as f:
    ohlcv = json.load(f)
if not isinstance(ohlcv, list):
    ohlcv = ohlcv.get('data', ohlcv.get('klines', ohlcv))

print(f"Stock: {symbol}  Bars: {len(ohlcv)}")

th12 = calc_v12(ohlcv)
v12 = detect_all_signals_v12(ohlcv, {'adaptive': th12, 'ob_displacement_mult': 1.0, 'require_volume': True})
thVP = vp_mod.calc_adaptive_thresholds(ohlcv)
vp = vp_mod.detect_all_signals_vPine(ohlcv, {'adaptive': thVP, 'ob_displacement_mult': 1.5, 'require_volume': True})

for key in ['FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear', 'Sweep_BSL', 'Sweep_SSL']:
    v12c = len(v12.get(key, []))
    vpc = len(vp.get(key, []))
    print(f"  {key:20s}: V12={v12c:3d}  V-Pine={vpc:3d}")

# Show OB methods
print("\nV12 OB method distribution:")
methods = {}
for s in v12.get('OB_Bull', []) + v12.get('OB_Bear', []):
    m = s.get('ob_method', 'unknown')
    methods[m] = methods.get(m, 0) + 1
for m, c in sorted(methods.items()):
    print(f"  {m}: {c}")
