# -*- coding: utf-8 -*-
"""Single-stock Eastmoney timing test."""
import io, json, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://quote.eastmoney.com/"}
t0 = time.time()
url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
       "secid=1.600519&klt=101&fqt=1&beg=20230101&end=20260820"
       "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
try:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    kl = (d.get("data") or {}).get("klines") or []
    print(f"600519: {len(kl)} bars in {time.time()-t0:.1f}s, latest {kl[-1].split(',')[0] if kl else '?'}")
except Exception as e:
    print(f"FAIL in {time.time()-t0:.1f}s: {e}")
