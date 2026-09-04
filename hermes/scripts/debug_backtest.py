#!/usr/bin/env python3
"""Test backtest_v4 return type"""
import json, os, sys
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)
from smc_engine_v4 import backtest_v4, detect_entries_v4

cache = os.path.expanduser('~/.hermes/kline_cache/920163_BJ_daily_300.json')
with open(cache) as f:
    bars = json.load(f)

# Ensure string t
for b in bars:
    if 't' in b and not isinstance(b['t'], str):
        b['t'] = str(b['t'])

params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}

# Test 1: entries
entries = detect_entries_v4(bars, params)
print(f"Entries type: {type(entries)}")
print(f"strict type: {type(entries.get('strict'))} value: {entries.get('strict')}")
print(f"total type: {type(entries.get('total'))} value: {entries.get('total')}")

# Test 2: backtest
trades = backtest_v4(bars, 'strict', params)
print(f"\nbacktest_v4 return type: {type(trades)}")
print(f"backtest_v4 return value: {trades}")

if isinstance(trades, list):
    print(f"len(trades)={len(trades)}")
    if trades:
        wins = [t for t in trades if t['pnl']>0]
        print(f"wins: {len(wins)}")
else:
    # This is the bug!
    import inspect
    source = inspect.getsource(backtest_v4)
    print(f"\nBUG FOUND! backtest_v4 returned {type(trades)}")
    print(f"Source (first 10 lines):")
    for line in source.split('\n')[:10]:
        print(f"  {line}")