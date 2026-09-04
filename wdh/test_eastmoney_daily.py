# -*- coding: utf-8 -*-
"""Test Eastmoney daily kline as Tencent replacement (does it have 8-19 data?)."""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
       "secid=1.600519&klt=101&fqt=1&beg=20260801&end=20260820"
       "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
req = urllib.request.Request(url, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
    kl = (d.get("data") or {}).get("klines") or []
    print("bars:", len(kl))
    for line in kl[-5:]:
        parts = line.split(",")
        print("  ", parts[0], "close:", parts[2])
except Exception as e:
    print("FAIL:", e)
