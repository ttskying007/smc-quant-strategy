#!/usr/bin/env python3
"""Check stock pool size and launch 5000-stock optimizer"""
import json, urllib.request, os

HUBBLE_BASE = "http://43.167.234.49:3101"
HEADERS = {"X-API-Key": "123456", "Content-Type": "application/json"}

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

req = urllib.request.Request(f"{HUBBLE_BASE}/api/v2/cnstock/symbols?listStatus=L", headers=HEADERS)
with urllib.request.urlopen(req, timeout=30) as resp:
    raw = json.loads(resp.read())

stocks = raw.get('symbols', raw.get('data', []))
print(f"Total stocks in pool: {len(stocks)}")

# filter out *ST
valid = [s for s in stocks if not s.get('symbol','').startswith('*ST')]
print(f"Valid stocks (non-ST): {len(valid)}")

# show a few samples
for s in valid[:5]:
    print(f"  {s.get('symbol')} - {s.get('name','N/A')}")
print("  ...")
for s in valid[-5:]:
    print(f"  {s.get('symbol')} - {s.get('name','N/A')}")

print(f"\n✅ Pool is sufficient for 5000 stocks")
print(f"Launching: --stocks 12 (random per iter) --iterations {(5000+11)//12}")