# -*- coding: utf-8 -*-
"""Test NetEase daily kline API (third data source after Tencent died + Eastmoney banned)."""
import io, json, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://quotes.money.163.com/"}

# NetEase: 600519 -> 0600519 (SZ=0, SH=1 prefix? Actually SH stocks use '0' + code? test both)
for code in ("0600519", "1600519"):
    url = f"https://quotes.money.163.com/service/chddata.html?code={code}&start=20260810&end=20260820&fields=TCLOSE;HIGH;LOW;TOPEN;VOTURNOVER"
    req = urllib.request.Request(url, headers=UA)
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read().decode("gbk", errors="replace")
        print(f"{code}: {len(b)} bytes in {time.time()-t0:.1f}s")
        lines = b.strip().split("\n")
        print("  header:", lines[0][:60])
        for l in lines[1:3]:
            print("  ", l[:80])
    except Exception as e:
        print(f"{code}: FAIL {e}")
    time.sleep(2)
