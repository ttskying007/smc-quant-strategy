# -*- coding: utf-8 -*-
"""拉取 2026-06~08 大宗交易历史 + 回测折价/溢价信号"""
import io, json, os, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = r"E:\test\smc_project\hermes\blocktrade_cache"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/"}
import datetime

# fetch by date range (single call returns all days in range, paginated)
def fetch_page(page):
    url = (f"https://datacenter-web.eastmoney.com/api/data/v1/get?"
           f"sortColumns=TRADE_DATE&sortTypes=-1&pageSize=500&pageNumber={page}"
           f"&reportName=RPT_DATA_BLOCKTRADE&columns=ALL"
           f"&filter=(TRADE_DATE%3E%27{datetime.date(2026,6,1)}%27)(TRADE_DATE%3C%27{datetime.date(2026,8,20)}%27)")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read())
    result = d.get("result") or {}
    return result.get("data") or [], result.get("pages") or 1

all_rows = []
page = 1
while True:
    rows, pages = fetch_page(page)
    all_rows.extend(rows)
    if page >= pages:
        break
    page += 1
    time.sleep(1.2)
    if page > 10:
        break
with open(os.path.join(OUT, "blocktrade_2026h2.json"), "w", encoding="utf-8") as fh:
    json.dump(all_rows, fh, ensure_ascii=False)
print(f"大宗交易: {len(all_rows)} 条（2026-06-01 ~ 08-19）", flush=True)
# sample premium distribution
from collections import Counter
prems = [float(r.get("PREMIUM_RATIO") or 0) for r in all_rows]
print(f"折溢价分布: 折价<0 {sum(1 for p in prems if p < 0)} | 溢价>0 {sum(1 for p in prems if p > 0)}")
print(f"折价样例: {sum(1 for p in prems if p < -10)} 条（折价>10%）")
