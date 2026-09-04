#!/usr/bin/env python3
"""Find 20 stocks with most OB signals for testing"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import CACHE_DIR, load_ohlcv
from v11.signals_v11 import detect_all_signals_v11

results = []
for f in list(CACHE_DIR.glob('*_60min_200.json'))[:200]:
    sym = f.stem.replace('_60min_200', '').replace('_', '.')
    ohlcv = load_ohlcv(sym)
    if not ohlcv:
        continue
    base_params = {'fvg_min_width': None, 'sweep_lookback': 12}
    sigs = detect_all_signals_v11(ohlcv, params=base_params, tf='60min')
    all_sigs = sigs.get('all', [])
    bull_ob = sum(1 for s in all_sigs if 'OB_Bull' in s.get('type','') and s.get('idx',0) >= 40)
    bull_fvg = sum(1 for s in all_sigs if 'FVG_Bull' in s.get('type','') and s.get('idx',0) >= 40)
    results.append((bull_ob, bull_fvg, sym, len(ohlcv)))

results.sort(key=lambda x: -x[0])

print(f"{'Symbol':12s} {'OB_Bull':>8s} {'FVG_Bull':>8s} {'Bars':>5s}")
print('-'*35)
for ob, fvg, sym, bars in results[:25]:
    print(f"{sym:12s} {ob:8d} {fvg:8d} {bars:5d}")
print(f'\nTotal stocks with OB_Bull>=3: {sum(1 for r in results if r[0] >= 3)}')
