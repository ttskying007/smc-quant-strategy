# -*- coding: utf-8 -*-
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
filt = urllib.parse.quote("(date='2026-08-14')")
url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&filter="
       + filt + "&pageNumber=1&pageSize=1&sortTypes=-1&sortColumns=date")
req = urllib.request.Request(url, headers=UA)
with urllib.request.urlopen(req, timeout=20) as r:
    d = json.loads(r.read())
rows = (d.get("result") or {}).get("data") or []
if rows:
    for k, v in sorted(rows[0].items()):
        print(f"{k}: {v}")
