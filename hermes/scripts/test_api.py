#!/usr/bin/env python3
"""Test Hubble API connectivity"""
import requests

patterns = [
    ("http://43.167.234.49:3101/api/kline/600519.SH?period=daily&count=300", {"X-API-Key": "123456"}),
    ("http://43.167.234.49:3101/api/kline/600519.SH?period=daily&count=300", {}),
    ("http://43.167.234.49:3101/api/kline?symbol=600519.SH&period=daily&count=300", {"X-API-Key": "123456"}),
    ("http://43.167.234.49:3101/kline/600519.SH?period=daily&count=300", {"X-API-Key": "123456"}),
    ("http://43.167.234.49:3101/kline/600519.SH/daily/300", {"X-API-Key": "123456"}),
    ("http://43.167.234.49:3101/v1/kline/600519.SH?period=daily&count=300", {"X-API-Key": "123456"}),
]

for url, headers in patterns:
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        print(f"URL: {url}")
        print(f"  Status: {resp.status_code}")
        print(f"  Body[:300]: {resp.text[:300]}")
    except Exception as e:
        print(f"URL: {url}")
        print(f"  Error: {e}")
    print()
