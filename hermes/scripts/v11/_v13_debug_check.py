#!/usr/bin/env python3
"""Debug V13 OB coverage on a few stocks."""
import json, sys
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v12 import detect_all_signals_v13_60min, detect_swings_v13_60min

CACHE = Path('/root/.hermes/kline_cache_60min')

# Pick 5 stocks from V467 full results
with open('/root/.hermes/smc_opt_v467/v467_full_stocks.json') as f:
    stocks = json.load(f)

test_syms = [s['symbol'] for s in stocks[:5]]
print("Testing symbols:", test_syms)

for sym in test_syms:
    cache_file = CACHE / f"{sym}.json"
    print(f"\n--- {sym} ---")
    print(f"  Cache file exists: {cache_file.exists()}")
    if not cache_file.exists():
        continue
    with open(cache_file) as f:
        data = json.load(f)
    print(f"  File keys: {list(data.keys())[:5]}")
    
    # Try different OHLCV paths
    ohlcv = None
    for key in ['data', 'klines', 'kline', 'ohlcv']:
        if key in data and len(data[key]) > 0:
            ohlcv = data[key]
            print(f"  Using key='{key}': {len(ohlcv)} bars")
            break
    
    if not ohlcv:
        print(f"  No OHLCV data found")
        continue
    
    print(f"  First bar keys: {list(ohlcv[0].keys())}")
    print(f"  First bar sample: {ohlcv[0]}")
    
    # Try V13
    result = detect_all_signals_v13_60min(ohlcv)
    obs = len(result.get('OB_Bull', [])) + len(result.get('OB_Bear', []))
    all_sigs = len(result.get('all', []))
    swing_h = len(result.get('swing_highs', []))
    swing_l = len(result.get('swing_lows', []))
    print(f"  V13: {obs} OB, {all_sigs} total signals, SH={swing_h} SL={swing_l}")
    
    # Show some OB details
    for ob_type in ['OB_Bull', 'OB_Bear']:
        for ob in result.get(ob_type, [])[:3]:
            meta = ob.get('metadata', {})
            print(f"    {ob_type} idx={ob['idx']} method={meta.get('ob_method','?')} disp={meta.get('displacement_ratio','?')}")
