#!/usr/bin/env python3
"""Check all cached intervals"""
from pathlib import Path
from collections import Counter

cache_dir = Path('/root/.hermes/kline_cache')
if not cache_dir.exists():
    cache_dir = Path('/root/.hermes/kline_cache_v11')

files = list(cache_dir.glob('*.json'))
print(f"Total files: {len(files)}")

intervals = Counter()
for f in files:
    parts = f.stem.rsplit('_', 2)
    if len(parts) >= 3:
        intervals[parts[-2]] += 1
    else:
        intervals['unknown'] += 1
for iv, cnt in sorted(intervals.items()):
    print(f"  {iv}: {cnt} files")
    
# Also check v11 cache
v11_dir = Path('/root/.hermes/kline_cache_v11')
if v11_dir.exists():
    v11_files = list(v11_dir.glob('*.json'))
    print(f"V11 cache: {len(v11_files)} files")
    for f in sorted(v11_files)[:5]:
        print(f"  {f.name}")
