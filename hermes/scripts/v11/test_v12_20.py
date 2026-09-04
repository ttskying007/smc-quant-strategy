#!/usr/bin/env python3
"""Compare V11 vs V12 OB detection on 20 stocks."""
import sys, json, os
sys.path.insert(0, '/root/.hermes/scripts/v11')
from signals_v11 import detect_all_signals_v11
from signals_v12 import detect_all_signals_v12, calc_adaptive_thresholds

cache_dir = '/root/.hermes/kline_cache_60min'
files = sorted(os.listdir(cache_dir))[:30]  # Try 30

results = []
for fname in files:
    if not fname.endswith('.json') or 'BJ' in fname:
        continue
    path = os.path.join(cache_dir, fname)
    with open(path) as f:
        ohlcv = json.load(f)
    if len(ohlcv) < 30:
        continue

    # V11
    v11 = detect_all_signals_v11(ohlcv)
    v11_ob = len([s for s in v11.get('all', []) if 'OB_Bull' in s.get('type', '')])
    v11_fvg = len([s for s in v11.get('all', []) if 'FVG_Bull' in s.get('type', '')])

    # V12
    adaptive = calc_adaptive_thresholds(ohlcv)
    v12 = detect_all_signals_v12(ohlcv, {'adaptive': adaptive, 'ob_displacement_mult': 1.3})
    v12_ob = len([s for s in v12.get('all', []) if 'OB_Bull' in s.get('type', '')])
    v12_fvg = len([s for s in v12.get('all', []) if 'FVG_Bull' in s.get('type', '')])
    n_sh = len(v12.get('swing_highs', []))
    n_sl = len(v12.get('swing_lows', []))

    results.append({
        'code': fname.replace('_SH_60min_200.json', '').replace('_SZ_60min_200.json', ''),
        'bars': len(ohlcv),
        'v11_ob': v11_ob, 'v12_ob': v12_ob,
        'v11_fvg': v11_fvg, 'v12_fvg': v12_fvg,
        'sh': n_sh, 'sl': n_sl,
    })

print(f"{'Code':8s} {'Bars':5s} {'V11OB':6s} {'V12OB':6s} {'Ratio':6s} {'V11FVG':7s} {'V12FVG':7s} {'SH':4s} {'SL':4s}")
print("-"*55)
for r in results[:20]:
    ratio = r['v12_ob'] / max(r['v11_ob'], 1)
    print(f"{r['code']:8s} {r['bars']:5d} {r['v11_ob']:6d} {r['v12_ob']:6d} {ratio:6.2f}x "
          f"{r['v11_fvg']:7d} {r['v12_fvg']:7d} {r['sh']:4d} {r['sl']:4d}")

# Summary
v11_total = sum(r['v11_ob'] for r in results)
v12_total = sum(r['v12_ob'] for r in results)
print(f"\n{'TOTAL':8s} {'':5s} {v11_total:6d} {v12_total:6d} {v12_total/max(v11_total,1):6.2f}x")
print(f"Avg OB per stock: V11={v11_total/len(results):.1f} V12={v12_total/len(results):.1f}")
