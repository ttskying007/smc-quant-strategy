# -*- coding: utf-8 -*-
"""拉取 2026-06~08 龙虎榜历史（约 2 个月，信号已有未来数据）"""
import io, json, os, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = r"E:\test\smc_project\hermes\lhb_cache"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/"}

# trading days 2026-06-01 to 2026-08-05 (roughly, will skip non-trading)
import datetime
dates = []
d = datetime.date(2026, 6, 1)
while d <= datetime.date(2026, 8, 5):
    if d.weekday() < 5:
        dates.append(d.strftime("%Y-%m-%d"))
    d += datetime.timedelta(days=1)
print(f"候选交易日: {len(dates)}", flush=True)

total = 0
ok_days = 0
for dt in dates:
    fn = dt.replace("-", "") + ".json"
    if os.path.exists(os.path.join(OUT, fn)):
        ok_days += 1
        continue
    url = (f"https://datacenter-web.eastmoney.com/api/data/v1/get?"
           f"sortColumns=SECURITY_CODE&sortTypes=1&pageSize=500&pageNumber=1"
           f"&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL"
           f"&filter=(TRADE_DATE%3D%27{dt}%27)")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        result = d.get("result") or {}
        rows = result.get("data") or []
        if rows:
            with open(os.path.join(OUT, fn), "w", encoding="utf-8") as fh:
                json.dump(rows, fh, ensure_ascii=False)
            ok_days += 1
            total += len(rows)
    except Exception as e:
        pass
    time.sleep(1.2)
print(f"DONE: {ok_days} 天 {total} 条（增量累计）", flush=True)
