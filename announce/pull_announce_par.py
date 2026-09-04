# -*- coding: utf-8 -*-
"""Parallel pull of full-market announcements (multi-threaded per day). Resume-capable."""
import concurrent.futures, io, json, os, sqlite3, sys, time, urllib.request

BASE = r"E:\test\smc_project\announce"
DB = os.path.join(BASE, "smc_announce.db")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:120]


def fetch_page(day, page, size=50, retries=4):
    url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
           f"sr=-1&page_size={size}&page_index={page}&ann_type=A&client_source=web"
           f"&begin_time={day}&end_time={day}")
    for attempt in range(retries):
        try:
            time.sleep(0.25)
            st, b = get(url)
            if st != 200:
                raise Exception(f"http {st}")
            d = json.loads(b)
            data = d.get("data") or {}
            return data.get("total_hits"), data.get("list") or []
        except Exception as e:
            if attempt == retries - 1:
                return None, str(e)[:80]
            time.sleep(1.5 * (attempt + 1))
    return None, "retries"


def fetch_day(day):
    total, rows = fetch_page(day, 1, 50)
    if total is None:
        return day, None, str(rows)
    out = list(rows)
    if total and total > 50:
        pages = min(-(-total // 50), 80)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(fetch_page, day, pg, 50) for pg in range(2, pages + 1)]
            for fut in concurrent.futures.as_completed(futs):
                c, r = fut.result()
                if isinstance(r, list):
                    out.extend(r)
    return day, out, None


def trading_days():
    p = r"E:\test\smc_project\hermes\kline_cache\600519_SH_daily_750.json"
    raw = json.load(open(p, encoding="utf-8"))
    days = []
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())
        if len(t) >= 8 and "20230101" <= t[:8] <= "20260814":
            days.append(f"{t[:4]}-{t[4:6]}-{t[6:8]}")
    return sorted(set(days))


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS announce (
        date TEXT, stock_code TEXT, stock_name TEXT, title TEXT, column_name TEXT, art_code TEXT,
        PRIMARY KEY(art_code))""")
    conn.commit()
    cur.execute("SELECT DISTINCT date FROM announce")
    done_days = {r[0] for r in cur.fetchall()}
    days = [d for d in trading_days() if d not in done_days]
    print(f"todo days: {len(days)} (already {len(done_days)})", flush=True)
    t0 = time.time()
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(fetch_day, d): d for d in days}
        for fut in concurrent.futures.as_completed(futs):
            day, rows, err = fut.result()
            done += 1
            if err:
                print(f"  {day} FAIL: {err}", flush=True)
                continue
            batch = []
            for a in rows:
                cols = ",".join(c.get("column_name", "") for c in (a.get("columns") or []))
                codes = a.get("codes") or []
                code = codes[0].get("stock_code", "") if codes else ""
                name = codes[0].get("short_name", "") if codes else ""
                batch.append((day, code, name, str(a.get("title") or ""), cols, a.get("art_code", "")))
            if batch:
                cur.executemany("INSERT OR REPLACE INTO announce VALUES (?,?,?,?,?,?)", batch)
                conn.commit()
            if done % 25 == 0:
                cur.execute("SELECT COUNT(*) FROM announce")
                print(f"  {done}/{len(days)} days, rows={cur.fetchone()[0]}, {time.time()-t0:.0f}s", flush=True)
    cur.execute("SELECT COUNT(*) FROM announce")
    print(f"DONE: {done} days, total rows={cur.fetchone()[0]} ({time.time()-t0:.0f}s)", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
