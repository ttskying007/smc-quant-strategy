#!/usr/bin/env python3
"""V6.2 全量扫描验证"""
import sys, os, json, time
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from pathlib import Path

d = json.load(open(Path.home() / '.hermes/smc_opt_v6/v61_signals_full.json'))
all_codes = [x['code'] for x in d['stocks']]
print(f"Total candidate codes: {len(all_codes)}")

from smc_engine_v62 import single_stock_scan_v62

# Best params from V6.2 test
params = {'fvg_th':0.11, 'score_th':1.5, 'sl_mult':3.86, 'tp_mult':0.43, 'min_sigs':4}

t0 = time.time()
results = {}
total_trades = 0
errors = 0

for i, code in enumerate(all_codes):
    if i % 100 == 0:
        elapsed = time.time() - t0
        rate = i / elapsed if elapsed > 0 else 0
        print(f"  [{i}/{len(all_codes)}] {total_trades} trades, {errors} err, {rate:.0f} stk/s")
    
    try:
        trades = single_stock_scan_v62(code, params)
        if trades:
            wins = sum(1 for t in trades if t['pnl'] > 0)
            wr = wins/len(trades)*100
            results[code] = {'n': len(trades), 'wins': wins, 'wr': round(wr, 1)}
            total_trades += len(trades)
    except Exception as e:
        errors += 1

elapsed = time.time() - t0
print(f"\nDone! {len(results)} stocks with signals, {errors} errors, {total_trades} total trades")
print(f"Time: {elapsed:.0f}s")

wrs = [v['wr'] for v in results.values()]
if wrs:
    print(f"Avg WR: {sum(wrs)/len(wrs):.1f}%")
    print(f"Median WR: {sorted(wrs)[len(wrs)//2]:.1f}%")
    print(f"WR>=90%: {sum(1 for w in wrs if w>=90)}/{len(wrs)}")
    print(f"Total trades: {total_trades}")
    print(f"Trades/stock avg: {total_trades/len(results):.1f}")

# Save
out = {'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'params': params, 
       'total_stocks': len(all_codes), 'stocks_with_signals': len(results),
       'total_trades': total_trades, 'errors': errors, 'results': results}
json.dump(out, open(Path.home() / '.hermes/smc_opt_v6/v62_signals_full.json', 'w'), indent=2)
print(f"\nSaved to v62_signals_full.json")