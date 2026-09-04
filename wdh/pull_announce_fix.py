# -*- coding: utf-8 -*-
"""补拉 8-15~8-20 公告（东财 np-anotice-stock）—— 修复公告数据滞后"""
import io, json, os, sys, time, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/notices/"}
DB = r"E:\test\smc_project\announce\smc_announce.db"

import sqlite3
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT MAX(date) FROM announce")
print("当前最新:", cur.fetchone()[0])


def fetch_notices(date):
    """东财公告列表 np-anotice-stock 按日期分页"""
    rows_all = []
    for page in (1, 2, 3, 4, 5, 6, 7, 8):
        url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
               f"sr=-1&page_size=100&page_index={page}&ann_type=A&client_source=web&"
               f"f_node=0&s_node=0&begin_time={urllib.parse.quote(date + ' 00:00:00')}&end_time={urllib.parse.quote(date + ' 23:59:59')}")
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read())
            data = (d.get("data") or {}).get("list") or []
            if not data:
                break
            rows_all.extend(data)
            if len(data) < 100:
                break
        except Exception as e:
            print(f"  page{page} FAIL: {str(e)[:50]}")
            break
        time.sleep(1.5)
    return rows_all


def save_day(rows, date):
    inserted = 0
    for a in rows:
        code = str(a.get("codes") or "").split(",")[0].strip()
        code = code.split(".")[0]
        title = a.get("title", "")
        name = a.get("art_code", "")
        # extract stock name if possible
        try:
            name = (a.get("stock_list") or [{}])[0].get("stock_name") or ""
        except Exception:
            pass
        if not code or not title:
            continue
        cur.execute("SELECT 1 FROM announce WHERE stock_code=? AND date=? AND title=?", (code, date, title))
        if cur.fetchone():
            continue
        cur.execute("INSERT INTO announce (date, stock_code, stock_name, title) VALUES (?,?,?,?)",
                    (date, code, name, title))
        inserted += 1
    conn.commit()
    return inserted


# pull 8-15 to 8-20
import datetime
d = datetime.date(2026, 8, 15)
while d <= datetime.date(2026, 8, 20):
    ds = d.strftime("%Y-%m-%d")
    rows = fetch_notices(ds)
    n = save_day(rows, ds)
    print(f"  {ds}: {len(rows)} 拉取, {n} 新增", flush=True)
    d += datetime.timedelta(days=1)
    time.sleep(2)

cur.execute("SELECT MAX(date) FROM announce")
print("更新后最新:", cur.fetchone()[0])
cur.execute("SELECT date, COUNT(*) FROM announce WHERE date >= '2026-08-15' GROUP BY date ORDER BY date")
for dd, c in cur.fetchall():
    print(f"  {dd}: {c} 条")
conn.close()
