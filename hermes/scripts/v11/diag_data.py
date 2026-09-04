#!/usr/bin/env python3
"""Diagnose: check data + V468 baseline on first 20 stocks"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')
from v11.v468_engine import CACHE_DIR, load_ohlcv

# Check data
count = with_data = 0
for f in sorted(CACHE_DIR.glob('*_60min_200.json'))[:20]:
    count += 1
    sym = f.stem.replace('_60min_200', '').replace('_', '.')
    data = load_ohlcv(sym)
    if data:
        with_data += 1
        print(f'{sym}: {len(data)} bars OK')
    else:
        d2 = json.loads(f.read_text())
        print(f'{sym}: {len(d2)} bars FAILS MIN_BARS=60')
print(f'---')
print(f'{with_data}/{count} with data >= 60 bars')
