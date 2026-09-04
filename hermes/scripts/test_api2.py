#!/usr/bin/env python3
"""Test Hubble V2 API"""
import requests

BASE = "http://43.167.234.49:3101"
HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

# List of endpoints to try
endpoints = [
    "/api/v2/kline/600519.SH?period=daily&count=300",
    "/api/v2/quote/600519.SH",
    "/api/v2/stocks",
    "/api/v2/market/quote/600519.SH",
    # Try original but with /
    "/api/kline?symbol=600519.SH&period=daily&count=300",
    "/api/v1/kline/600519.SH?period=daily&count=300",
]

for ep in endpoints:
    url = BASE + ep
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        print(f"[{resp.status_code}] {ep}")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                # Show keys and a snippet
                print(f"  Keys: {list(data.keys())[:5]}")
                klines = data.get('data', data.get('result', []))
                if klines and isinstance(klines, list):
                    print(f"  Bars: {len(klines)}")
                    if len(klines) > 0:
                        print(f"  First: {klines[0]}")
                        print(f"  Last: {klines[-1]}")
                else:
                    print(f"  Data: {str(data)[:200]}")
            else:
                print(f"  Data: {str(data)[:200]}")
        else:
            print(f"  Body: {resp.text[:200]}")
    except Exception as e:
        print(f"[ERR] {ep}: {e}")
    print()
