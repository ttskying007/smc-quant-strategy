#!/usr/bin/env python3
"""Compare V11 vs V12 OB with different displacement multipliers."""
import sys, json, os
sys.path.insert(0, '/root/.hermes/scripts/v11')
from signals_v11 import detect_all_signals_v11
from signals_v12 import detect_all_signals_v12, calc_adaptive_thresholds

cache_dir = '/root/.hermes/kline_cache_60min'
files = sorted(os.listdir(cache_dir))[:30]

for mult in [0.8, 1.0, 1.3]:
    results = []
    for fname in files:
        if not fname.endswith('.json') or 'BJ' in fname:
            continue
        with open(os.path.join(cache_dir, fname)) as f:
            ohlcv = json.load(f)
        if len(ohlcv) < 30:
            continue
        
        adaptive = calc_adaptive_thresholds(ohlcv)
        v12 = detect_all_signals_v12(ohlcv, {'adaptive': adaptive, 'ob_displacement_mult': mult})
        v12_ob = len([s for s in v12.get('all', []) if 'OB_Bull' in s.get('type', '')])
        
        v11 = detect_all_signals_v11(ohlcv)
        v11_ob = len([s for s in v11.get('all', []) if 'OB_Bull' in s.get('type', '')])
        
        results.append({'code': fname.split('_')[0], 'v11': v11_ob, 'v12': v12_ob})
    
    total_v11 = sum(r['v11'] for r in results)
    total_v12 = sum(r['v12'] for r in results)
    avg_v11 = total_v11 / len(results)
    avg_v12 = total_v12 / len(results)
    zero_count = sum(1 for r in results if r['v12'] == 0)
    
    print(f"displacement_mult={mult}: V12 avg={avg_v12:.1f} (V11 avg={avg_v11:.1f}) "
          f"ratio={total_v12/max(total_v11,1)*100:.0f}% zeros={zero_count}/{len(results)}")
    
    if mult == 1.0:
        print(f"\n  Per-stock (mult=1.0):")
        for r in results:
            print(f"  {r['code']:6s} V11={r['v11']:3d} V12={r['v12']:3d} ({r['v12']/max(r['v11'],1)*100:.0f}%)")
