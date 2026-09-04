# -*- coding: utf-8 -*-
"""Pull full-market announcements 2023-01-01..2026-08-14 (title-level, Lane A/B base).
Eastmoney np-anotice-stock API, per-day, paginated. SQLite output.
"""
import io, json, os, sqlite3, sys, time, urllib.request, urllib.parse

BASE = r"E:\test\smc_project\announce"
os.makedirs(BASE, exist_ok=True)
DB = os.path.join(BASE, "smc_announce.db")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:120]


def fetch_day(date, page=1, size=50, retries=4):
    url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
           f"sr=-1&page_size={size}&page_index={page}&ann_type=A&client_source=web"
           f"&begin_time={date}&end_time={date}")
    for attempt in range(retries):
        try:
            time.sleep(0.4)
            st, b = get(url)
            if st != 200:
                raise Exception(f"http {st}")
            d = json.loads(b)
            data = d.get("data") or {}
            return data.get("total_hits"), data.get("list") or []
        except Exception as e:
            if attempt == retries - 1:
                return None, str(e)[:100]
            time.sleep(2.0 * (attempt + 1))
    return None, "retries"


def trading_days():
    p = r"E:\test\smc_project\hermes\kline_cache\600519_SH_daily_750.json"
    raw = json.load(open(p, encoding="utf-8"))
    days = []
    for r in raw:
        t = str(r.get("t") or "")
        digits = "".join(c for c in t if c.isdigit())
        if len(digits) >= 8 and "20230101" <= digits[:8] <= "20260814":
            days.append(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
    return sorted(set(days))


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS announce (
        date TEXT, stock_code TEXT, stock_name TEXT, title TEXT, column_name TEXT, art_code TEXT,
        PRIMARY KEY(art_code))""")
    conn.commit()
    days = trading_days()
    print("trading days:", len(days), flush=True)
    done = 0
    t0 = time.time()
    for day in days:
        total, rows = fetch_day(day, 1, 50)
        if total is None:
            print(f"  {day} FAIL: {rows}", flush=True)
            continue
        all_rows = list(rows)
        if total and total > 50:
            pages = -(-total // 50)
            for pg in range(2, min(pages, 60) + 1):
                _, pr = fetch_day(day, pg, 50)
                if isinstance(pr, list):
                    all_rows.extend(pr)
                time.sleep(0.3)
        batch = []
        for a in all_rows:
            cols = ",".join(c.get("column_name", "") for c in (a.get("columns") or []))
            codes = a.get("codes") or []
            code = codes[0].get("stock_code", "") if codes else ""
            name = codes[0].get("short_name", "") if codes else ""
            batch.append((day, code, name, str(a.get("title") or ""), cols, a.get("art_code", "")))
        cur.executemany("INSERT OR REPLACE INTO announce VALUES (?,?,?,?,?,?)", batch)
        conn.commit()
        done += 1
        if done % 50 == 0:
            cur.execute("SELECT COUNT(*) FROM announce")
            print(f"  {done}/{len(days)} days, rows={cur.fetchone()[0]}, {time.time()-t0:.0f}s", flush=True)
    cur.execute("SELECT COUNT(*) FROM announce")
    print(f"DONE: {done} days, {cur.fetchone()[0]} rows in {DB} ({time.time()-t0:.0f}s)")
    conn.close()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
