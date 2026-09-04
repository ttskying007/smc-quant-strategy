#!/usr/bin/env python3
"""Check cache vs result codes"""
import json, os
cache_dir = '/root/.hermes/kline_cache'
cache_files = set(f.replace('_daily_300.json','') for f in os.listdir(cache_dir) if f.endswith('_daily_300.json'))
print(f"Cache files: {len(cache_files)}")
print(f"Sample cache: {list(cache_files)[:5]}")

with open('/root/.hermes/smc_opt_v4/scan_v4_results.json') as f:
    results = json.load(f)
print(f"Result stocks: {len(results)}")

# Check code format difference
for r in results[:10]:
    code = r['code']
    cache_key = code.replace('.','_').replace('-','_')
    in_cache = cache_key in cache_files
    print(f"  {code} -> cache_key={cache_key} in_cache={in_cache}")

# Find a match
matches = sum(1 for r in results[:100] if r['code'].replace('.','_').replace('-','_') in cache_files)
print(f"\nMatching: {matches}/100")