#!/usr/bin/env python3
"""Compare V12 vs V-Pine signal detection on a single stock."""
import json, sys, os
sys.path.insert(0, '/root/.hermes/scripts')
os.chdir('/root/.hermes/scripts/v11')

# Load V12
from signals_v12 import detect_all_signals_v12, calc_adaptive_thresholds as calc_v12

# Load V-Pine with proper module setup
import importlib.util
import types

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

with open('/root/.hermes/kline_cache_60min/600997_SH_60min_200.json') as f:
    ohlcv = json.load(f)
if not isinstance(ohlcv, list):
    ohlcv = ohlcv.get('data', ohlcv.get('klines', ohlcv))

print(f"Stock: 600997.SH  Bars: {len(ohlcv)}")
print(f"Time range: {ohlcv[0]['t']} to {ohlcv[-1]['t']}")

# V12 signals
th12 = calc_v12(ohlcv)
v12 = detect_all_signals_v12(ohlcv, {'adaptive': th12, 'ob_displacement_mult': 1.0, 'require_volume': True})

# V-Pine signals
thVP = vp_mod.calc_adaptive_thresholds(ohlcv)
vp = vp_mod.detect_all_signals_vPine(ohlcv, {'adaptive': thVP, 'ob_displacement_mult': 1.5, 'require_volume': True})

# Compare by type
key_types = ['FVG_Bull', 'FVG_Bear', 'OB_Bull', 'OB_Bear', 
             'Sweep_BSL', 'Sweep_SSL', 'CHOCH_Bull', 'CHOCH_Bear',
             'MSS', 'IFVG_Bull', 'IFVG_Bear']

print("\n=== Signal Counts ===")
for key in key_types:
    v12c = len(v12.get(key, []))
    vpc = len(vp.get(key, []))
    print(f"  {key:20s}: V12={v12c:3d}  V-Pine={vpc:3d}")

# Detailed OB comparison
print("\n=== V12 OB_Bull (first 10) ===")
for s in v12.get('OB_Bull', [])[:10]:
    print(f"  idx={s['idx']:3d} price={s['lower']:.3f}-{s['upper']:.3f}(mid={s['price']:.3f}) "
          f"str={s['strength']:.1f} dis={s.get('displacement_ratio', 0):.2f} "
          f"method={s.get('ob_method','?')} sw_idx={s.get('swing_high_idx','?')}")

print("\n=== V-Pine OB_Bull (first 10) ===")
for s in vp.get('OB_Bull', [])[:10]:
    print(f"  idx={s['idx']:3d} price={s['lower']:.3f}-{s['upper']:.3f}(mid={s['price']:.3f}) "
          f"str={s['strength']:.1f} dis={s.get('displacement_ratio', 0):.2f} "
          f"type={s.get('ob_type','?')} sw_idx={s.get('swing_idx','?')}")

# Show the context around first few OBs
print("\n=== Price context around V12 OB_Bull[0] ===")
s = v12.get('OB_Bull', [])
if s:
    idx = s[0]['idx']
    for j in range(max(0,idx-3), min(len(ohlcv), idx+6)):
        b = ohlcv[j]
        marker = ' <-- OB' if j == idx else ''
        print(f"  [{j:3d}] o={b['o']:.3f} h={b['h']:.3f} l={b['l']:.3f} c={b['c']:.3f} dir={'BEAR' if b['c']<b['o'] else 'BULL' if b['c']>b['o'] else 'DOJI'}{marker}")

print("\n=== Price context around V-Pine OB_Bull[0] ===")
s = vp.get('OB_Bull', [])
if s:
    idx = s[0]['idx']
    for j in range(max(0,idx-3), min(len(ohlcv), idx+6)):
        b = ohlcv[j]
        marker = ' <-- OB' if j == idx else ''
        print(f"  [{j:3d}] o={b['o']:.3f} h={b['h']:.3f} l={b['l']:.3f} c={b['c']:.3f} dir={'BEAR' if b['c']<b['o'] else 'BULL' if b['c']>b['o'] else 'DOJI'}{marker}")
