# -*- coding: utf-8 -*-
"""Retry cninfo announcement query with proper params (per-stock, szse+shse)."""
import io, json, sys, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def post(url, data, timeout=20):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "http://www.cninfo.com.cn/new/disclosure/stock",
        "Origin": "http://www.cninfo.com.cn",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:150]


# cninfo stock announcement query - 600519 with szse column
queries = [
    {"pageNum": 1, "pageSize": 5, "column": "szse", "tabName": "fulltext", "plate": "",
     "stock": "600519,gssz0000519", "searchkey": "", "secid": "", "category": "", "trade": "",
     "seDate": "", "sortName": "", "sortType": "", "isHLtitle": "true"},
    {"pageNum": 1, "pageSize": 5, "column": "szse", "tabName": "fulltext", "plate": "sh",
     "stock": "600519,9900024215", "searchkey": "", "secid": "", "category": "", "trade": "",
     "seDate": "", "sortName": "", "sortType": "", "isHLtitle": "true"},
    {"pageNum": 1, "pageSize": 5, "column": "szse", "tabName": "fulltext", "plate": "sh",
     "stock": "600519", "searchkey": "", "secid": "", "category": "category_ndbg_szsh", "trade": "",
     "seDate": "", "sortName": "", "sortType": "", "isHLtitle": "true"},
]
for i, q in enumerate(queries):
    st, b = post("http://www.cninfo.com.cn/new/hisAnnouncement/query", q)
    if st == 200:
        try:
            d = json.loads(b)
            anns = d.get("announcements") or []
            print(f"q{i+1}: total={d.get('totalAnnouncement')} anns={len(anns)}")
            for a in anns[:3]:
                print("   ", a.get("announcementTitle", "")[:60], "|", a.get("adjunctUrl", "")[:40])
        except Exception as e:
            print(f"q{i+1}: parse err {e} | {b[:200]}")
    else:
        print(f"q{i+1}: FAIL {b}")
