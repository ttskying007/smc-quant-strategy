# -*- coding: utf-8 -*-
"""Test Sina realtime quote (hq.sinajs.cn) - needed for 1-min price monitoring."""
import io, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}

# Sina realtime: var hq_str_sh600519="name,open,prevclose,current,high,low,..."
url = "https://hq.sinajs.cn/list=sh600519,sz000001"
req = urllib.request.Request(url, headers=UA)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        b = r.read().decode("gbk", errors="replace")
    print("raw:", b[:200])
    # parse
    for line in b.strip().split("\n"):
        if "hq_str_" in line:
            parts = line.split('="', 1)
            sym = parts[0].split("_")[-1]
            vals = parts[1].rstrip('";').split(",")
            if len(vals) > 10:
                name = vals[0]
                cur = vals[3]  # current price
                high = vals[4]
                low = vals[5]
                print(f"{sym} {name}: current={cur} high={high} low={low}")
except Exception as e:
    print("FAIL:", e)
