# -*- coding: utf-8 -*-
"""Pull full-market margin (RZRQ) history 2023-01-01..latest from Eastmoney into SQLite.

Trading calendar derived from local kline_cache (600519 daily bars).
PIT note: margin data for day T is disclosed after close on T, usable at T+1 decision.
"""
import concurrent.futures, io, json, os, sqlite3, sys, time, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = r"E:\test\smc_project\margin"
os.makedirs(BASE, exist_ok=True)
DB = os.path.join(BASE, "smc_margin.db")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Referer": "https://data.eastmoney.com/", "Accept": "application/json, text/plain, */*"}
START = "20230101"   # 8-digit comparison (kline dates are YYYYMMDD)
END = "20260814"     # local data epoch date


def trading_days():
    """Derive trading calendar from local kline dates (8-digit YYYYMMDD)."""
    p = r"E:\test\smc_project\hermes\kline_cache\600519_SH_daily_750.json"
    if not os.path.exists(p):
        p = r"E:\test\smc_project\hermes\kline_cache\600519.SH_daily_750.json"
    raw = json.load(open(p, encoding="utf-8"))
    days = []
    for r in raw:
        t = str(r.get("t") or r.get("date") or "")
        digits = "".join(c for c in t if c.isdigit())
        if len(digits) >= 8 and START <= digits[:8] <= END:
            days.append(digits[:8])
    return sorted(set(days))


def fetch_day(date, page=1, size=500, retries=4):
    filt = urllib.parse.quote(f"(date='{date[:4]}-{date[4:6]}-{date[6:8]}')")
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&filter="
           + filt + f"&pageNumber={page}&pageSize={size}&sortTypes=-1&sortColumns=date")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read())
            res = d.get("result") or {}
            data = res.get("data") or []
            if data or res.get("count"):
                return res.get("count"), data
            # empty -> likely rate limited; back off
            time.sleep(2.0 * (attempt + 1))
        except Exception as e:
            if attempt == retries - 1:
                return None, str(e)[:120]
            time.sleep(2.0 * (attempt + 1))
    return None, "empty after retries"


def pull_date(date):
    """Pull one full trading day -> list of rows."""
    time.sleep(0.25)  # polite rate limiting
    total, rows = fetch_day(date, 1, 500)
    if total is None:
        return date, None, str(rows)
    out = rows
    if total and total > 500:
        pages = -(-total // 500)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(fetch_day, date, pg, 500) for pg in range(2, pages + 1)]
            for fut in concurrent.futures.as_completed(futures):
                c, r = fut.result()
                if r:
                    out.extend(r)
    return date, out, None


def main():
    days = trading_days()
    print("trading days:", len(days), days[0], "->", days[-1])
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS margin_daily (
        date TEXT, scode TEXT, secname TEXT, secucode TEXT, market TEXT,
        rzye REAL, rqyl REAL, rqye REAL, rzmre REAL, rzche REAL, rzjme REAL,
        rqmcl REAL, rqjmg REAL, rqchl REAL, rzyezb REAL, rzrqye REAL,
        rchange3dcp REAL, rchange5dcp REAL, rchange10dcp REAL,
        rzmre3d REAL, rzjme3d REAL, rzjme5d REAL, spj REAL, sz REAL, zdf REAL,
        PRIMARY KEY(date, scode))""")
    conn.commit()
    done = 0
    t0 = time.time()
    for d in days:
        # skip if already present
        cur.execute("SELECT COUNT(*) FROM margin_daily WHERE date=?", (d,))
        if cur.fetchone()[0] > 0:
            done += 1
            continue
        date, rows, err = pull_date(d)
        if err:
            print(f"  {d} FAIL: {err}", flush=True)
            continue
        if not rows:
            print(f"  {d} empty (non-trading?)", flush=True)
            continue
        batch = []
        for r in rows:
            batch.append((
                d, r.get("SCODE"), r.get("SECNAME"), r.get("SECUCODE"), r.get("MARKET"),
                r.get("RZYE"), r.get("RQYL"), r.get("RQYE"), r.get("RZMRE"), r.get("RZCHE"),
                r.get("RZJME"), r.get("RQMCL"), r.get("RQJMG"), r.get("RQCHL"), r.get("RZYEZB"),
                r.get("RZRQYE"), r.get("RCHANGE3DCP"), r.get("RCHANGE5DCP"), r.get("RCHANGE10DCP"),
                r.get("RZMRE3D"), r.get("RZJME3D"), r.get("RZJME5D"), r.get("SPJ"), r.get("SZ"), r.get("ZDF"),
            ))
        cur.executemany("INSERT OR REPLACE INTO margin_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
        conn.commit()
        done += 1
        if done % 30 == 0:
            cur.execute("SELECT COUNT(*) FROM margin_daily")
            print(f"  {done}/{len(days)} days, rows={cur.fetchone()[0]}, {time.time()-t0:.0f}s", flush=True)
    cur.execute("SELECT COUNT(*) FROM margin_daily")
    total_rows = cur.fetchone()[0]
    print(f"DONE: {done}/{len(days)} days, {total_rows} rows in {DB} ({time.time()-t0:.0f}s)")
    conn.close()


if __name__ == "__main__":
    main()
