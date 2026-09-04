# -*- coding: utf-8 -*-
import io, json, os, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
kt = r"E:\test\smc_project\hermes\kline_cache_tencent"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.sina.com.cn/"}
# pick 10 stocks at 8/18
syms = []
for f in sorted(os.listdir(kt)):
    if not f.endswith("_daily_800.json"):
        continue
    raw = json.load(open(os.path.join(kt, f), encoding="utf-8"))
    if raw and str(raw[-1].get("t", "")) == "20260818":
        syms.append(f.replace("_daily_800.json", "").replace("_", "."))
    if len(syms) >= 10:
        break
print(f"测试 {len(syms)} 只（当前停在 8/18）:")
ok = 0
for s in syms:
    c, ex = s.split(".")
    sina = ("sh" if ex == "SH" else "sz") + c
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina}&scale=240&ma=no&datalen=10"
    try:
        time.sleep(0.2)
        b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read().decode("utf-8", "replace")
        d = json.loads(b)
        days = [x.get("day") for x in d]
        last = days[-1] if days else "?"
        has820 = "2026-08-20" in days
        if has820:
            ok += 1
        print(f"  {s}: 最新 {last} 含8/20={has820}")
    except Exception as e:
        print(f"  {s}: FAIL {str(e)[:40]}")
print(f"OK: {ok}/10")
