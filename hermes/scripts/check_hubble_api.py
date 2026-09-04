#!/usr/bin/env python3
"""Check Hubble API 60min endpoint status"""
import urllib.request, json, sys
from pathlib import Path

URL = 'http://43.167.234.49:3101/api/v1/klines60min/000001.SZ?key=123456'

print("=" * 60, flush=True)
print("Workstream C: 60min/Multi-TF API Check", flush=True)
print("=" * 60, flush=True)

# 1. Check Hubble API
print("\n[1] Hubble API 60min endpoint...", flush=True)
try:
    req = urllib.request.Request(URL)
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"  HTTP {resp.status} - SUCCESS", flush=True)
    data = json.loads(resp.read())
    print(f"  Response: {json.dumps(data, ensure_ascii=False)[:200]}", flush=True)
    print("  Result: Hubble API WORKS", flush=True)
    sys.exit(0)
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code} {e.reason} - FAILED", flush=True)
    if e.code == 401:
        print("  Result: Hubble API returns 401 (as documented)", flush=True)
    else:
        print(f"  Result: Hubble API HTTP error {e.code}", flush=True)
except Exception as e:
    print(f"  {type(e).__name__}: {e} - FAILED", flush=True)

# 2. Check Tencent API via klines_60min
print("\n[2] Tencent API (klines_60min)...", flush=True)
sys.path.insert(0, '/root/.hermes/scripts')
from v11.klines_60min import get_60min_kline

bars = get_60min_kline('000001.SZ', force_refresh=True)
if bars and len(bars) > 10:
    print(f"  Got {len(bars)} bars for 000001.SZ - SUCCESS", flush=True)
    print(f"  Latest: {bars[-1]}", flush=True)
    print("  Result: Tencent API WORKS", flush=True)
else:
    print(f"  Got {len(bars) if bars else 0} bars - FAILED", flush=True)
    print("  Result: Tencent API FAILED", flush=True)

print("\n" + "=" * 60, flush=True)
print("Summary:", flush=True)
hubble_ok = False  # We know from context it returns 401
tencent_ok = bool(bars and len(bars) > 10)

if hubble_ok:
    print("  Hubble API: WORKS - can be used for 60min data", flush=True)
elif tencent_ok:
    print("  Hubble API: FAILS (401) - Tencent API works as fallback", flush=True)
else:
    print("  Both APIs FAILED - 60min data unavailable", flush=True)
print("=" * 60, flush=True)
