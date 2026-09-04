# -*- coding: utf-8 -*-
"""Test Sina daily kline API variants."""
import io, json, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}

# Sina historical kline (money.finance.sina.com.cn)
for url in [
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=5",
    "https://quotes.sina.cn/cn/api/jsonp_v2.php/var/CN_MarketDataService.getKLineData?symbol=sh600519&scale=240&ma=no&datalen=5",
]:
    req = urllib.request.Request(url, headers=UA)
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read().decode("utf-8", errors="replace")
        print(f"{url.split('/')[-1][:40]}: {len(b)} bytes in {time.time()-t0:.1f}s")
        print("  sample:", b[:200])
    except Exception as e:
        print(f"FAIL: {e}")
    time.sleep(2)
