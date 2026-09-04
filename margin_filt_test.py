# -*- coding: utf-8 -*-
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:200]


for filt in ["(date='2026-08-14')", "(DATE='2026-08-14')", "(trade_date='2026-08-14')", "(scode=\"600519\")"]:
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&filter="
           + urllib.parse.quote(filt) + "&pageNumber=1&pageSize=5&sortTypes=-1&sortColumns=date")
    st, b = get(url)
    if st == 200:
        try:
            d = json.loads(b)
            res = d.get("result") or {}
            rows = res.get("data") or []
            print(filt, "-> count:", res.get("count"), "rows:", len(rows))
            if rows:
                print("   sample:", {k: rows[0].get(k) for k in ("date", "SCODE", "SECNAME", "RZYE", "RQYL") if k in rows[0]})
                print("   keys:", sorted(rows[0].keys())[:15])
        except Exception as e:
            print(filt, "parse err", e)
    else:
        print(filt, "FAIL", b)
