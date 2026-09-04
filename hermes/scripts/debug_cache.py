#!/usr/bin/env python3
"""Debug: check cache format and test single stock"""
import json, os, sys
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))

# 1. Check cache format
cache = os.path.expanduser('~/.hermes/kline_cache')
files = os.listdir(cache)
print(f"Cache files: {len(files)}")
if files:
    f = files[0]
    with open(os.path.join(cache, f)) as fp:
        data = json.load(fp)
    print(f"Sample: {f}")
    print(f"Type: {type(data)}, Len: {len(data) if isinstance(data,list) else 'dict'}")
    if isinstance(data, list) and len(data) > 0:
        item = data[0]
        print(f"Keys: {list(item.keys())}")
        print(f"Sample: {item}")
        # Check t field
        if 't' in item:
            print(f"t sample: {item['t']}")

# 2. Test single stock extraction
print("\n--- Testing single stock extraction ---")
from smc_engine_v4 import get_klines, detect_entries_v4, backtest_v4, get_volatility_profile, get_adaptive_params

# Test with direct API call (no cache)
bars = get_klines('000001.SZ', 'daily', 300)
print(f"Direct API bars: {len(bars) if bars else 0}")
if bars and len(bars) > 10:
    print(f"Keys: {list(bars[0].keys())}")
    print(f"t sample: {bars[0].get('t','N/A')}")
    
    vol = get_volatility_profile(bars)
    print(f"Vol: {vol}")
    
    params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}
    
    entries = detect_entries_v4(bars, params)
    print(f"Entries keys: {list(entries.keys())}")
    strict = entries.get('strict', [])
    total = entries.get('total', [])
    print(f"Strict entries: {len(strict)}")
    print(f"Total entries: {len(total)}")
    if strict:
        e = strict[0]
        print(f"Entry sample: {json.dumps(e, default=str)}")
    
    trades = backtest_v4(bars, 'strict', params)
    print(f"Strict trades: {len(trades) if trades else 0}")
else:
    print(f"No bars returned!")
    # Try without proxy
    import urllib.request
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
        print(f"  Remove {k}")
    bars2 = get_klines('000001.SZ', 'daily', 300)
    print(f"Retry bars: {len(bars2) if bars2 else 0}")