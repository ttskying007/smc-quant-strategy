# -*- coding: utf-8 -*-
"""Test single-day full-market margin (RZRQ) pull from Eastmoney."""
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Referer": "https://data.eastmoney.com/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:200]


def fetch_day(date, page=1, size=500):
    """date=2026-08-14; returns (total, rows)"""
    filt = urllib.parse.quote(f'(date=\'{date}\')')
    url = (f"https://datacenter-web.eastmoney.com/api/data/v1/get?"
           f"reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&filter={filt}"
           f"&pageNumber={page}&pageSize={size}&sortTypes=-1&sortColumns=DATE,SCODE")
    st, body = get(url)
    if st != 200:
        return None, None
    try:
        d = json.loads(body)
        res = d.get("result") or {}
        return res.get("count"), res.get("data") or []
    except Exception as e:
        return None, str(e)


# test one recent day
for date in ("2026-08-14", "2026-01-05", "2023-01-03"):
    total, rows = fetch_day(date)
    print(f"=== {date}: total={total}, rows_fetched={len(rows) if rows else 0} ===")
    if rows:
        r = rows[0]
        print("  fields:", sorted(r.keys())[:40])
        print("  sample:", {k: r.get(k) for k in ("DATE", "SCODE", "SECNAME", "RZYE", "RQYL", "RZMRE", "RZCHE", "RZJME", "RZRQYE")})
        # how many pages needed
        if total:
            import math
            print("  pages_needed:", math.ceil(total / 500))
    print()
