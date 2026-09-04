#!/usr/bin/env python3
"""Test akshare 60min data download"""
import sys, json
sys.path.insert(0, '/root/.hermes/scripts')

try:
    import akshare as ak
    # Test 60min for 000001.SZ
    df = ak.stock_zh_a_hist_min_em(symbol="000001", period="60", 
                                    start_date="20260101", end_date="20260508", adjust="")
    print(f"OK: {len(df)} rows, columns={list(df.columns)}")
    
    # Convert to standard format
    records = []
    for _, row in df.iterrows():
        records.append({
            't': row['时间'],
            'o': float(row['开盘']),
            'h': float(row['最高']),
            'l': float(row['最低']),
            'c': float(row['收盘']),
            'v': float(row['成交量']),
        })
    
    # Save test cache
    import json as j
    cache_path = '/root/.hermes/kline_cache/000001_SZ_60min_500.json'
    j.dump(records[-500:], open(cache_path, 'w'))
    print(f"Saved {min(500, len(records))} bars to {cache_path}")
    
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
