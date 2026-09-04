# -*- coding: utf-8 -*-
import json, io, sys, os, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
# pick a stock at 8/18
kt = r"E:\test\smc_project\hermes\kline_cache_tencent"
for f in os.listdir(kt):
    if not f.endswith("_daily_800.json"):
        continue
    raw = json.load(open(os.path.join(kt, f), encoding="utf-8"))
    if raw and str(raw[-1].get("t", "")) == "20260818":
        code = f.replace("_daily_800.json", "").replace("_", ".")
        c, ex = code.split(".")
        sina = ("sh" if ex == "SH" else "sz") + c
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina}&scale=240&ma=no&datalen=10"
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "replace")
            d = json.loads(b)
            days = [x.get("day") for x in d]
            print(f"{code}: 本地最新 8/18 | 新浪返回: {days[-5:]}")
        except Exception as e:
            print(f"{code}: 拉取失败 {str(e)[:60]}")
        break
