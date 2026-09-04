# -*- coding: utf-8 -*-
"""Backfill missing announcement days (serial, long delay, resume-capable).
Run after main pull: finds dates with 0 rows in DB and retries them slowly."""
import io, json, os, sqlite3, sys, time, urllib.request

BASE = r"E:\test\smc_project\announce"
DB = os.path.join(BASE, "smc_announce.db")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://data.eastmoney.com/notices/"}


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:
        return None, str(e)[:100]


def fetch_page(day, page, size=50):
    url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
           f"sr=-1&page_size={size}&page_index={page}&ann_type=A&client_source=web"
           f"&begin_time={day}&end_time={day}")
    st, b = get(url)
    if st != 200:
        return None, None
    d = json.loads(b)
    data = d.get("data") or {}
    return data.get("total_hits"), data.get("list") or []


def fetch_day(day):
    time.sleep(2.0)  # long serial delay to avoid rate-limit
    total, rows = fetch_page(day, 1, 50)
    if total is None:
        return None
    out = list(rows)
    if total and total > 50:
        pages = min(-(-total // 50), 80)
        for pg in range(2, pages + 1):
            time.sleep(1.0)
            _, pr = fetch_page(day, pg, 50)
            if pr:
                out.extend(pr)
    return out


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
    cur.execute("SELECT DISTINCT date FROM announce")
    have = {r[0] for r in cur.fetchall()}
    missing = [d for d in trading_days() if d not in have]
    print(f"missing days: {len(missing)}", flush=True)
    filled = 0
    for day in missing:
        rows = fetch_day(day)
        if rows is None:
            print(f"  {day} STILL FAIL", flush=True)
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
            filled += 1
        if filled % 20 == 0:
            print(f"  filled {filled}/{len(missing)}", flush=True)
    print(f"DONE: filled {filled}/{len(missing)}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
