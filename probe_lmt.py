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


base = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.600519&klt=60&fqt=1"
        "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
for params in ["&lmt=1000", "&beg=20250101&end=20260814&lmt=5000", "&lmt=5000&end=20260814"]:
    st, b = get(base + params)
    if st == 200:
        try:
            d = json.loads(b)
            kl = (d.get("data") or {}).get("klines") or []
            print(params, "-> bars:", len(kl), "| first:", kl[0] if kl else "-", "| last:", kl[-1] if kl else "-")
        except Exception as e:
            print(params, "err", e)
    else:
        print(params, "FAIL", b)
