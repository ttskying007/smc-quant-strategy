#!/usr/bin/env python3
"""Full test: scan 200 stocks and verify signal quality."""
import json, sys, time
sys.path.insert(0, '/root/.hermes/scripts/v25')
from pathlib import Path
from collections import Counter
from smc_core_pine_like import detect_all_signals_pine_like

# List stocks from K-line cache
cache = Path('/root/.hermes/kline_cache')
stocks = sorted([f.stem.replace('_daily_300','').replace('_', '.') for f in cache.glob('*_daily_300.json')])
print(f'Total stocks in cache: {len(stocks)}')

# Test first 50
test_stocks = stocks[:50]
t0 = time.time()
results = []

for i, sym in enumerate(test_stocks):
    sym_file = sym.replace('.', '_')
    fp = cache / f'{sym_file}_daily_300.json'
    if not fp.exists():
        continue
    data = json.loads(fp.read_bytes())
    if len(data) < 80:
        continue
    
    res = detect_all_signals_pine_like(data)
    sig = res['signals']
    sm = res['summary']
    
    obs = sig['obs']
    sweeps = sig['sweeps']
    struct = sig['structure']
    
    ob_count = len(obs)
    ob_with_disp = sum(1 for ob in obs if ob.get('displacement_ratio', 0) >= 1.0)
    
    results.append({
        'sym': sym, 'bars': len(data),
        'ob': ob_count, 'sweep': len(sweeps),
        'struct': len(struct),
        'fvg': sm['n_fvg'],
        'swing_h': sm['n_swing_highs'],
        'swing_l': sm['n_swing_lows'],
        'eql': sm['n_eqh_eql'],
    })

total_time = time.time() - t0
print(f'\nScanned {len(results)} stocks in {total_time:.1f}s')

# Summary
total_ob = sum(r['ob'] for r in results)
stocks_with_ob = sum(1 for r in results if r['ob'] > 0)
avg_ob = total_ob / max(len(results), 1)
print(f'\n=== Signal Detection Summary (50 stocks) ===')
print(f'Stocks with OB:        {stocks_with_ob}/{len(results)} ({stocks_with_ob/max(len(results),1)*100:.0f}%)')
print(f'Total OBs:             {total_ob} (avg {avg_ob:.1f}/stock)')
print(f'Total Sweeps:          {sum(r["sweep"] for r in results)}')
print(f'Total Structure evts:  {sum(r["struct"] for r in results)}')
print(f'Total FVGs:            {sum(r["fvg"] for r in results)}')
print(f'Total EQL/EQH:         {sum(r["eql"] for r in results)}')

# Top stocks by signal count
print(f'\n=== Top 10 stocks by OB count ===')
for r in sorted(results, key=lambda x: -x['ob'])[:10]:
    print(f'  {r["sym"]:12s} OB={r["ob"]:2d} Sweep={r["sweep"]:2d} Struct={r["struct"]:2d} FVG={r["fvg"]:2d}')
