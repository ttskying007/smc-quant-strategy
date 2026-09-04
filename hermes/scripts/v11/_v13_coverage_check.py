#!/usr/bin/env python3
"""Compare V13 relaxed OB coverage vs V11 baseline on 100 stocks."""
import json, sys
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v12 import detect_all_signals_v13_60min
from v11.signals_v11 import detect_all_signals_v11

CACHE = Path('/root/.hermes/kline_cache_60min')

with open('/root/.hermes/smc_opt_v467/v467_full_stocks.json') as f:
    stocks = json.load(f)

def cache_file(sym):
    return CACHE / f"{sym.replace('.', '_')}_60min_200.json"

stock_ids = [s['symbol'] for s in stocks[:100]]

v11_obs_total = 0
v13_total = 0
v11_stocks = 0
v13_stocks = 0
n_loaded = 0
results = []

for sym in stock_ids:
    cf = cache_file(sym)
    if not cf.exists():
        continue
    with open(cf) as f:
        ohlcv = json.load(f)
    if not ohlcv or len(ohlcv) < 60:
        continue
    n_loaded += 1

    try:
        r11 = detect_all_signals_v11(ohlcv)
        # V11 uses flat 'ob' key with type field
        v11_obs = len([s for s in r11.get('ob', []) if 'OB' in s.get('type','')])
    except Exception as e:
        v11_obs = 0

    try:
        r13 = detect_all_signals_v13_60min(ohlcv)
        v13_obs = len(r13.get('OB_Bull', [])) + len(r13.get('OB_Bear', []))
    except Exception as e:
        v13_obs = 0

    v11_obs_total += v11_obs
    v13_total += v13_obs
    if v11_obs > 0: v11_stocks += 1
    if v13_obs > 0: v13_stocks += 1
    results.append((sym, v11_obs, v13_obs))

print(f"Loaded {n_loaded} stocks")
print(f"V11 baseline:  {v11_obs_total} OB across {v11_stocks}/{n_loaded} stocks (avg {v11_obs_total/max(n_loaded,1):.1f}/stock)")
print(f"V13 relaxed:   {v13_total} OB across {v13_stocks}/{n_loaded} stocks (avg {v13_total/max(n_loaded,1):.1f}/stock)")
if v11_obs_total > 0:
    print(f"V13/V11 ratio: {v13_total/v11_obs_total*100:.1f}%")
    print(f"Gap: {v11_obs_total - v13_total} OB ({100-v13_total/v11_obs_total*100:.0f}%)")
print(f"\nTop 15 by V11 OB count:")
results.sort(key=lambda r: -r[1])
for sym, v11c, v13c in results[:15]:
    bar = "\u2588" * min(v13c, 40) if v13c else "-"
    print(f"  {sym:10s} V11={v11c:3d} V13={v13c:3d} {bar}")
print(f"\nBottom 15 by V13/V11 ratio:")
results.sort(key=lambda r: (1-r[2]/max(r[1],1))*100)  
for sym, v11c, v13c in results[-15:]:
    ratio = v13c / max(v11c, 1) * 100
    print(f"  {sym:10s} V11={v11c:3d} V13={v13c:3d} V13/V11={ratio:.0f}%")
