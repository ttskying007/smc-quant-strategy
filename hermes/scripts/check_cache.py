#!/usr/bin/env python3
"""Check kline cache format"""
import json

d = json.loads(open("/root/.hermes/kline_cache/600519_SH_daily_300.json").read())
print(f"Keys in entry: {list(d[0].keys())}")
print(f"First entry: {d[0]}")
print(f"Last entry: {d[-1]}")
print(f"Total: {len(d)} entries")

# Check what keys exist
for k in ["date", "t", "timestamp", "time", "ts"]:
    if k in d[0]:
        print(f"Date key '{k}': {d[0][k]}")
    else:
        print(f"No '{k}' key in data")
