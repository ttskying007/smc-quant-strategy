# -*- coding: utf-8 -*-
"""Test Eastmoney announcement content endpoint for notice_content text (per v628 history)."""
import io, json, sys, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}

# known announcement art_code (earnings preannouncement from our announce DB)
# query our DB for a 业绩预告 with art_code
import sqlite3
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT date, stock_code, title, art_code FROM announce WHERE title LIKE '%业绩预告%' AND art_code IS NOT NULL LIMIT 3")
rows = cur.fetchall()
conn.close()
print("sample announcements:", [(r[0], r[1], str(r[2])[:30], r[3]) for r in rows])

if rows:
    art = rows[0][3]
    url = f"https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={art}&client_source=web&page_index=1"
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        data = d.get("data") or {}
        print("\ncontent keys:", list(data.keys()))
        for k in ("notice_content", "content", "summary", "articleContent", "attach_list"):
            if k in data:
                v = data[k]
                s = str(v)
                print(f"  {k}: len={len(s)}, sample: {s[:300]}")
    except Exception as e:
        print("FAIL:", e)
