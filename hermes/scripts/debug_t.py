#!/usr/bin/env python3
"""Fix: t field could be int"""
import json, os
cache = '/root/.hermes/kline_cache/920163_BJ_daily_300.json'
with open(cache) as f:
    bars = json.load(f)
print(f"Bars: {len(bars)}")
for i, b in enumerate(bars[:5]):
    t = b.get('t')
    print(f"  {i}: t={t} type={type(t).__name__}")
    # Test: str(t) vs t[:10]
    t_str = str(t)
    print(f"    str(t)={t_str} len={len(t_str)} sub={t_str[:4] if len(t_str)>=4 else t_str}")