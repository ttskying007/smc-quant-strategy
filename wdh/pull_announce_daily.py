# -*- coding: utf-8 -*-
"""每日公告增量拉取（pull_announce_daily.py）
拉取最近 N 天公告（默认 3 天，覆盖周末），增量入库（去重）。
加入 daily_combo_run 防止公告滞后（修复 8-14 滞后教训）"""
import datetime, io, json, os, sqlite3, sys, time, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/notices/"}
DB = r"E:\test\smc_project\announce\smc_announce.db"


def fetch_notices(date):
    rows_all = []
    # FIX(2026-09-05, 审计 G10): 分页到空为止（原 6 页×100=600 条截断，A股日均 2000-6000 条，
    # 财报季漏检 40-80% —— "近月无新股"的原料端根因之一）
    for page in range(1, 80):
        url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
               f"sr=-1&page_size=100&page_index={page}&ann_type=A&client_source=web&"
               f"f_node=0&s_node=0&begin_time={urllib.parse.quote(date + ' 00:00:00')}&end_time={urllib.parse.quote(date + ' 23:59:59')}")
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            data = (d.get("data") or {}).get("list") or []
            if not data:
                break
            rows_all.extend(data)
            if len(data) < 100:
                break
        except Exception:
            break
        time.sleep(0.6)  # FIX(2026-08-22): 1.2s->0.6s sleep (faster; Eastmoney tolerant at low rate)
    return rows_all


def extract_code(a):
    codes = a.get("codes") or []
    if isinstance(codes, list) and codes and isinstance(codes[0], dict):
        sc = codes[0].get("stock_code") or codes[0].get("inner_code") or ""
        name = codes[0].get("short_name") or ""
        return str(sc).split(".")[0], name
    return "", ""


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1, help="拉取最近 N 天（默认 1 天快速；周末后手动 --days 3）")
    args = ap.parse_args()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM announce")
    cur_max = cur.fetchone()[0] or ""
    print(f"DB 当前最新: {cur_max}", flush=True)
    start = datetime.date.today() - datetime.timedelta(days=args.days)
    # FIX(2026-09-05, 审计 G09): 去掉"当日已最新则跳过"短路 —— 晚间公告(16:00-22:00)次日才可见
    # 导致实盘 T+2 入场；改为始终拉取当天，(date,code,title) 增量去重，可 20:00/21:30 补拉
    d = start
    total = 0
    while d <= datetime.date.today():
        ds = d.strftime("%Y-%m-%d")
        rows = fetch_notices(ds)
        inserted = 0
        for a in rows:
            code, name = extract_code(a)
            title = a.get("title", "")
            if not code or not title:
                continue
            cur.execute("SELECT 1 FROM announce WHERE stock_code=? AND date=? AND title=?", (code, ds, title))
            if cur.fetchone():
                continue
            cur.execute("INSERT INTO announce (date, stock_code, stock_name, title) VALUES (?,?,?,?)",
                        (ds, code, name, title))
            inserted += 1
        conn.commit()
        total += inserted
        print(f"  {ds}: {len(rows)} 拉取, {inserted} 新增", flush=True)
        d += datetime.timedelta(days=1)
        time.sleep(1)  # FIX(2026-08-22): 2s->1s between days
    cur.execute("SELECT MAX(date) FROM announce")
    print(f"DONE: 新增 {total} 条, DB 最新 {cur.fetchone()[0]}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
