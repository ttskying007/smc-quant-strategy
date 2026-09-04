#!/usr/bin/env python3
"""Quick data check"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v38 import CACHE_DIR

symbols = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
print(f'Total symbols: {len(symbols)}')
print(f'First 5: {symbols[:5]}')

f = CACHE_DIR / f'{symbols[0].replace(".","_")}_daily_300.json'
data = json.loads(f.read_text())
print(f'Sample data len: {len(data)} bars')
print(f'Keys: {list(data[0].keys())}')
print(f'Sample last bar: {data[-1]}')
