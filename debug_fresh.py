# -*- coding: utf-8 -*-
import json, io, sys, os, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
kt = r"E:\test\smc_project\hermes\kline_cache_tencent"
sample = None
for f in os.listdir(kt):
    if not f.endswith("_daily_800.json"):
        continue
    raw = json.load(open(os.path.join(kt, f), encoding="utf-8"))
    if raw and str(raw[-1].get("t", "")) != "20260820":
        sample = f
        break
if not sample:
    print("全部最新 8/20")
    sys.exit()
raw = json.load(open(os.path.join(kt, sample), encoding="utf-8"))
print(f"{sample}: 本地最新 {raw[-1].get('t')} ({len(raw)} bars)")
code = sample.replace("_daily_800.json", "").replace("_", ".")
c, ex = code.split(".")
sina = ("sh" if ex == "SH" else "sz") + c
url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina}&scale=240&ma=no&datalen=5"
try:
    b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read().decode("utf-8", "replace")
    d = json.loads(b)
    print(f"新浪实时最新: {[x.get('day') for x in d[-3:]]}")
except Exception as e:
    print(f"新浪拉取失败: {str(e)[:60]}")
