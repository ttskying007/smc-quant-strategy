#!/usr/bin/env python3
"""Check symbol matching between quality ratings and kline cache"""
import json
from pathlib import Path

q = json.loads(Path('/root/.hermes/smc_signals/stock_quality_ratings.json').read_text())
ab = {s['symbol'] for s in q['stocks'] if s['tier'] in ('A','B')}

cache = Path('/root/.hermes/kline_cache')
cached = set()
for f in cache.glob('*_daily_300.json'):
    sym = f.stem.replace('_daily_300','').replace('_','.')
    cached.add(sym)

intersection = ab & cached
print(f"A/B symbols: {len(ab)}")
print(f"Cached files: {len(cached)}")
print(f"Intersection: {len(intersection)}")
print(f"A/B not in cache: {len(ab - cached)}")
print(f"Cache not in A/B: {len(cached - ab)}")

print("\nSample A/B symbols:", sorted(list(ab))[:10])
print("Sample cached symbols:", sorted(list(cached))[:10])
print("Sample intersection:", sorted(list(intersection))[:10])

# Check for format mismatch
ab_sample = sorted(list(ab))[:20]
cached_sample = sorted(list(cached))[:20]
print("\nA/B format examples:", ab_sample)
print("Cache format examples:", cached_sample)

# Check some specific symbols
for sym in ['603129.SH', '603788.SH', '300329.SZ']:
    in_c = sym in cached
    in_ab = sym in ab
    print(f"  {sym}: in_cache={in_c}, in_ab={in_ab}")
