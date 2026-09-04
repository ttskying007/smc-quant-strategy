# -*- coding: utf-8 -*-
"""Probe Eastmoney announcement API for title-level event research (Lane A/B)."""
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:150]


# 1. announcement list for a specific stock (600519) - recent
url = "https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=20&page_index=1&ann_type=A&client_source=web&stock_list=600519"
st, b = get(url)
if st == 200:
    d = json.loads(b)
    data = d.get("data") or {}
    lst = data.get("list") or []
    print("600519 公告数:", len(lst), "| total:", data.get("total_hits"))
    for a in lst[:10]:
        print("  ", a.get("art_code"), "|", a.get("notice_date", "")[:10], "|",
              str(a.get("title") or a.get("art_title") or "")[:80])
else:
    print("FAIL:", b)

# 2. try columns/type filter - performance forecast (业绩预告)
print("\n=== 业绩预告类别测试 ===")
url2 = "https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=5&page_index=1&ann_type=A&client_source=web&stock_list=600519&column=szse&category=szse_gplyb"
st2, b2 = get(url2)
if st2 == 200:
    d2 = json.loads(b2)
    lst2 = ((d2.get("data") or {}).get("list")) or []
    print("  category 过滤结果:", len(lst2))
    for a in lst2[:5]:
        print("   ", a.get("notice_date", "")[:10], "|", str(a.get("title") or "")[:80])
else:
    print("  FAIL:", b2)

# 3. test full-market announcement list (no stock filter) - one day
print("\n=== 全市场公告（8-14） ===")
url3 = "https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=10&page_index=1&ann_type=A&client_source=web&begin_time=2026-08-14&end_time=2026-08-14"
st3, b3 = get(url3)
if st3 == 200:
    d3 = json.loads(b3)
    data3 = d3.get("data") or {}
    lst3 = data3.get("list") or []
    print("  全市场 8-14 公告:", len(lst3), "| total:", data3.get("total_hits"))
    for a in lst3[:5]:
        cols = ",".join(c.get("column_name", "") for c in (a.get("columns") or []))
        print("   ", a.get("notice_date", "")[:10], "|", str(a.get("title") or "")[:70], "|", cols[:40])
else:
    print("  FAIL:", b3)
