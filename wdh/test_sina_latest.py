# -*- coding: utf-8 -*-
"""Sina kline: check if it has 8-19 data (latest trading day)."""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}
url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=2000"
req = urllib.request.Request(url, headers=UA)
with urllib.request.urlopen(req, timeout=20) as r:
    b = r.read().decode("utf-8", errors="replace")
d = json.loads(b)
print("bars:", len(d))
print("latest:", d[-1]["day"], "close:", d[-1]["close"])
print("prev:", d[-2]["day"])
