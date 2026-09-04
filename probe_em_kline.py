# -*- coding: utf-8 -*-
import io, json, sys, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://quote.eastmoney.com/"}


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:150]


# Eastmoney 60min kline with beg/end
url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
       "secid=1.600519&klt=60&fqt=1&beg=20230101&end=20260814"
       "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
st, b = get(url)
if st == 200:
    try:
        d = json.loads(b)
        data = d.get("data") or {}
        kl = data.get("klines") or []
        print("东财 60min bars:", len(kl))
        if kl:
            print("  first:", kl[0])
            print("  last:", kl[-1])
        print("  name:", data.get("name"), "| code:", data.get("code"))
    except Exception as e:
        print("parse err:", str(e)[:100], b[:300])
else:
    print("FAIL:", b)

# also test daily kline same API (for reference)
url2 = url.replace("klt=60", "klt=101")
st2, b2 = get(url2)
if st2 == 200:
    d2 = json.loads(b2)
    kl2 = (d2.get("data") or {}).get("klines") or []
    print("\n东财 daily bars (reference):", len(kl2))
    if kl2:
        print("  first:", kl2[0], "| last:", kl2[-1])
