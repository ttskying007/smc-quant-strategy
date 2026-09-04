# -*- coding: utf-8 -*-
"""Light single-request Sina test (avoid triggering rate limit)."""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}
url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=3"
req = urllib.request.Request(url, headers=UA)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        b = r.read().decode("utf-8", errors="replace")
    d = json.loads(b)
    print("OK:", len(d), "bars, latest:", d[-1]["day"])
except Exception as e:
    print("FAIL:", e)
