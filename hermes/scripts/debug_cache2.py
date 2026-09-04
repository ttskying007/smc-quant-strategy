#!/usr/bin/env python3
"""Debug load_bars_from_cache"""
import json, sys, os
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

# Direct import the function
from pathlib import Path
KLINE_CACHE = Path.home() / '.hermes' / 'kline_cache'

def load_bars_from_cache(symbol, limit=300):
    cache_key = f"{symbol}_daily_{limit}".replace('.','_').replace('-','_')
    cache_path = KLINE_CACHE / f"{cache_key}.json"
    print(f"  Looking for: {cache_path}")
    print(f"  Exists: {cache_path.exists()}")
    if cache_path.exists():
        size = os.path.getsize(cache_path)
        print(f"  Size: {size}")
        if size > 100:
            try:
                with open(cache_path) as f:
                    bars = json.load(f)
                print(f"  Loaded: {len(bars)} bars")
                return bars
            except Exception as e:
                print(f"  Error: {e}")
    
    print(f"  Cache miss! Trying API...")
    from smc_engine_v4 import get_klines
    bars = get_klines(symbol, 'daily', limit)
    print(f"  API returned: {len(bars) if bars else 0} bars")
    return bars

# Test
print("Testing load_bars_from_cache:")
bars = load_bars_from_cache('920163.BJ', 300)
print(f"Result: {type(bars)}, bars: {len(bars) if bars else 0}")

if bars and len(bars) > 0:
    print(f"First bar keys: {list(bars[0].keys())}")
    
    from smc_engine_v4 import detect_entries_v4, backtest_v4, get_volatility_profile
    vol = get_volatility_profile(bars)
    print(f"Vol: {vol}")
    
    params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}
    entries = detect_entries_v4(bars, params)
    print(f"Entries: L={len(entries.get('loose',[]))} T={len(entries.get('total',[]))} S={len(entries.get('strict',[]))}")
    
    trades = backtest_v4(bars, 'strict', params)
    print(f"Trades: {len(trades) if trades else 0}")