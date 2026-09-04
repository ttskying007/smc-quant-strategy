#!/usr/bin/env python3
"""Check available cache data"""
import json
from pathlib import Path

cache_dir = Path('/root/.hermes/kline_cache')
if cache_dir.exists():
    files = list(cache_dir.glob('*.json'))
    print(f"Total cache files: {len(files)}")
    # Group by interval
    from collections import Counter
    intervals = Counter()
    for f in files:
        parts = f.stem.split('_')
        if len(parts) >= 3:
            intervals[parts[-2]] += 1
    for interval, count in sorted(intervals.items()):
        print(f"  {interval}: {count} files")
    
    # Show a few sample files
    print(f"\nSample files:")
    for f in sorted(files)[:10]:
        try:
            d = json.loads(f.read_text())
            print(f"  {f.name}: {len(d)} bars, keys={list(d[0].keys()) if d else 'empty'}")
        except:
            print(f"  {f.name}: ERROR")
else:
    print("No cache dir found")
