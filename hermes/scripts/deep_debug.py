#!/usr/bin/env python3
"""Deep debug: test V4 detection on cached data"""
import json, sys, os
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_engine_v4 import (
    detect_entries_v4, backtest_v4, get_volatility_profile,
    detect_fvg_standard, detect_sweep_precise
)

# Load from cache
cache = '/root/.hermes/kline_cache/000001_SZ_daily_300.json'
with open(cache) as f:
    bars = json.load(f)
print(f"Bars: {len(bars)}")
print(f"Sample keys: {list(bars[0].keys())}")
print(f"Sample bar: {bars[0]}")

# Test vol profile
vol = get_volatility_profile(bars)
print(f"Vol: {vol}")

# Test FVG detection
fvg = detect_fvg_standard(bars, 0.26)
print(f"FVG found: {len(fvg) if fvg else 0}")

# Test sweep detection
sweep = detect_sweep_precise(bars)
print(f"Sweep found: {len(sweep) if sweep else 0}")

# Test full entry detection
params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}
entries = detect_entries_v4(bars, params)
print(f"Entries: loose={len(entries.get('loose',[]))} total={len(entries.get('total',[]))} strict={len(entries.get('strict',[]))}")

# Test backtest
trades = backtest_v4(bars, 'strict', params)
print(f"Strict trades: {len(trades) if trades else 0}")

# Try with higher Klines
print("\n--- With 600 Klines (direct API) ---")
from smc_engine_v4 import get_klines
bars600 = get_klines('000001.SZ', 'daily', 600)
if bars600 and len(bars600) > 100:
    print(f"Bars: {len(bars600)}")
    entries600 = detect_entries_v4(bars600, params)
    print(f"Entries600: loose={len(entries600.get('loose',[]))} total={len(entries600.get('total',[]))} strict={len(entries600.get('strict',[]))}")
    trades600 = backtest_v4(bars600, 'strict', params)
    print(f"Strict trades600: {len(trades600) if trades600 else 0}")
    if trades600:
        wins = sum(1 for t in trades600 if t['pnl']>0)
        print(f"WR: {wins/len(trades600)*100:.1f}%")

# Try with 400 Klines
print("\n--- With 400 Klines ---")
bars400 = get_klines('000001.SZ', 'daily', 400)
if bars400 and len(bars400) > 100:
    entries400 = detect_entries_v4(bars400, params)
    print(f"Entries400: L={len(entries400.get('loose',[]))} T={len(entries400.get('total',[]))} S={len(entries400.get('strict',[]))}")
    trades400 = backtest_v4(bars400, 'strict', params)
    print(f"Strict trades400: {len(trades400) if trades400 else 0}")