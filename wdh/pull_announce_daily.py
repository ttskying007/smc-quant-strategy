# -*- coding: utf-8 -*-
"""每日公告增量拉取（pull_announce_daily.py）
拉取最近 N 天公告（默认 3 天，覆盖周末），增量入库（去重）。
加入 daily_combo_run 防止公告滞后（修复 8-14 滞后教训）"""
import datetime, io, json, os, sqlite3, sys, time, urllib.request, urllib.parse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "research"))
import config as CFG
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/notices/"}
DB = CFG.ANNOUNCE_DB
os.makedirs(os.path.dirname(DB), exist_ok=True)


def fetch_notices(date):
    rows_all = []
    # FIX(2026-09-05, 审计 G10): 分页到空为止（原 6 页×100=600 条截断，A股日均 2000-6000 条，
    # 财报季漏检 40-80% —— "近月无新股"的原料端根因之一）
    # FIX(2026-09-19, 实际超时 A/B): 串行 0.6s×80页 → ~500s/day; daily_combo_run timeout=600s
    # 完全吃掉 margin, 实测 09-15~19 中断。改用并行 graphdataserver, 目标 <60s/日.
    # 模式: '首轮' 8页并行快筛; 若未找到短页(<100), 继续逐段并行直到空为止.
    import concurrent.futures as _cf
    UA2 = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://data.eastmoney.com/notices/"}

    def _fetch_page(p):
        url = ("https://np-anotice-stock.eastmoney.com/api/security/ann?"
               f"sr=-1&page_size=100&page_index={p}&ann_type=A&client_source=web&"
               f"f_node=0&s_node=0&begin_time={urllib.parse.quote(date + ' 00:00:00')}&end_time={urllib.parse.quote(date + ' 23:59:59')}")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA2), timeout=15) as r:
                data = json.loads(r.read())
            return (data.get("data") or {}).get("list") or []
        except Exception:
            return []

    page = 1
    batch = 8
    while True:
        with _cf.ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(_fetch_page, p) for p in range(page, page + batch)]
            results = [f.result() for f in _cf.as_completed(futs)]
        results.sort(key=len, reverse=True)
        short = None
        for rows in results:
            if not rows:
                short = True
                break
            rows_all.extend(rows)
            if len(rows) < 100:
                short = True
                break
        if short:
            break
        page += batch
        if page > 200:
            break  # 上限防御(单日 ~20000 条)
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
