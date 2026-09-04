# -*- coding: utf-8 -*-
"""修复：清理错误 stock_code 的公告 + 按正确格式重新拉取 8-15~8-20"""
import io, json, os, sqlite3, sys, time, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/notices/"}
DB = r"E:\test\smc_project\announce\smc_announce.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1. delete broken rows (stock_code starting with [{' or ann_type)
cur.execute("DELETE FROM announce WHERE stock_code LIKE \"[{'%\" OR stock_code LIKE 'ann_type%' OR stock_code='[{'")
print("删除错误记录:", cur.rowcount)
cur.execute("DELETE FROM announce WHERE date >= '2026-08-15'")
print("清空 8-15 起（重拉）:", cur.rowcount)
conn.commit()


def fetch_notices(date):
    rows_all = []
    for page in range(1, 9):
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
        except Exception:
            break
        time.sleep(1.5)
    return rows_all


def extract_code(a):
    """codes = [{'inner_code':..., 'stock_code': '301308', 'short_name':...}]"""
    codes = a.get("codes") or []
    if isinstance(codes, list) and codes and isinstance(codes[0], dict):
        sc = codes[0].get("stock_code") or codes[0].get("inner_code") or ""
        name = codes[0].get("short_name") or ""
        return str(sc).split(".")[0], name
    return "", ""


def save_day(rows, date):
    inserted = 0
    for a in rows:
        code, name = extract_code(a)
        title = a.get("title", "")
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
cur.execute("SELECT date, COUNT(*) FROM announce WHERE date >= '2026-08-17' GROUP BY date ORDER BY date")
for dd, c in cur.fetchall():
    print(f"  {dd}: {c} 条")
conn.close()
