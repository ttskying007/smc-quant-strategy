# -*- coding: utf-8 -*-
import io, json, sys, time, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Referer": "https://data.eastmoney.com/", "Accept": "application/json, text/plain, */*"}


def fetch(date, page=1, size=500):
    filt = urllib.parse.quote(f"(date='{date}')")
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&filter="
           + filt + f"&pageNumber={page}&pageSize={size}&sortTypes=-1&sortColumns=date")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read())
    res = d.get("result") or {}
    return res.get("count"), (res.get("data") or [])


# single retry after cooldown
time.sleep(3)
for date in ("2026-08-14", "2026-08-13"):
    for attempt in range(3):
        try:
            total, rows = fetch(date)
            print(date, "-> total:", total, "rows:", len(rows), "sample:", rows[0].get("SCODE") if rows else "-")
            if rows:
                break
        except Exception as e:
            print(date, "attempt", attempt, "ERR:", str(e)[:100])
        time.sleep(5)
    time.sleep(5)
