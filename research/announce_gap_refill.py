# -*- coding: utf-8 -*-
"""增量公告补缺: 并行取 page 1..8, 单日幂等, 用于留守几个落数日(09-15/16/18/19)。
用法: python research/announce_gap_refill.py 20260917 20260918 ...
若日期缺省,自动找 deltas;单日耗时 ~40s。
"""
import datetime, io, json, os, sqlite3, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import urllib.request, urllib.parse
import concurrent.futures

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import config as CFG
DB = CFG.ANNOUNCE_DB

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/notices/"}


def fetch_page(date, page):
    url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1"
           "&page_size=100&page_index=%d&ann_type=A&client_source=web&f_node=0&s_node=0"
           "&begin_time=%s&end_time=%s") % (page,
                urllib.parse.quote(date + " 00:00:00"), urllib.parse.quote(date + " 23:59:59"))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            return json.loads(r.read()).get("data", {}).get("list") or []
    except Exception:
        return []


def pull_day(date_iso, max_pages=10):
    """单日全部 page 取回(可能上百条/日); 含幂等 INSERT(基于 date+code+title 主键)"""
    rows_all = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(fetch_page, date_iso, p) for p in range(1, max_pages + 1)]
        results = [f.result() for f in concurrent.futures.as_completed(futs)]
    results.sort(key=len, reverse=True)
    for rows in results:
        if not rows:
            continue
        rows_all.extend(rows)
        if len(rows) < 100:
            break
    return rows_all


def insert_day(conn, date_iso, rows):
    cur = conn.cursor()
    ins = 0
    for a in rows:
        codes = a.get("codes") or []
        if isinstance(codes, list) and codes and isinstance(codes[0], dict):
            sc = codes[0].get("stock_code") or codes[0].get("inner_code") or ""
            name = codes[0].get("short_name") or ""
            code = str(sc).split(".")[0] or ""
        else:
            continue
        title = a.get("title", "")
        if not code or not title:
            continue
        cur.execute("SELECT 1 FROM announce WHERE stock_code=? AND date=? AND title=?",
                    (code, date_iso, title))
        if cur.fetchone():
            continue
        cur.execute("INSERT INTO announce (date, stock_code, stock_name, title) VALUES (?,?,?,?)",
                    (date_iso, code, name, title))
        ins += 1
    conn.commit()
    return ins


def main(dates=None):
    conn = sqlite3.connect(DB)
    if not dates:
        cur = conn.cursor()
        cur.execute("SELECT MAX(date) FROM announce")
        maxd = cur.fetchone()[0] or "2023-01-01"
        ref = datetime.date.fromisoformat(maxd)
        today = datetime.date.today()
        dates = []
        while ref < today:
            ref += datetime.timedelta(days=1)
            if ref.weekday() < 5:
                dates.append(ref.strftime("%Y-%m-%d"))
    print("待拉日:", dates)
    for ds in dates:
        t0 = time.time()
        rows = pull_day(ds, max_pages=10)
        ins = insert_day(conn, ds, rows)
        print(f"  {ds}: 拉={len(rows)} 入={ins} ({time.time()-t0:.1f}s)", flush=True)
        time.sleep(1)
    conn.close()
    print("OK")


if __name__ == "__main__":
    main(sys.argv[1:])
