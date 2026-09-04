# -*- coding: utf-8 -*-
"""Announcement event pilot: performance forecast / buyback events vs market baseline.
Using existing announcement data (2023H2-2024Q1). Event window T+1..T+10.
Check if positive events have alpha (excess vs equal-weight market)."""
import io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

# load stock klines lazily
cache = {}
def closes_of(symbol):
    if symbol not in cache:
        # match kline file by code prefix (e.g. 600519 -> 600519_SH_daily_800.json)
        import glob
        cands = glob.glob(os.path.join(KT, f"{symbol}_*_daily_800.json"))
        if not cands:
            cache[symbol] = None
            return None
        p = cands[0]
        raw = json.load(open(p, encoding="utf-8"))
        c = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("c"):
                c.append((t, float(r["c"])))
        c.sort()
        cache[symbol] = c
    return cache[symbol]


def window_ret(symbol, event_date, days=10):
    cl = closes_of(symbol)
    if not cl:
        return None
    dates = [x[0] for x in cl]
    # event date -> find next trading day after event
    nxt = [d for d in dates if d > event_date]
    if not nxt:
        return None
    i = dates.index(nxt[0])
    if i + days >= len(cl):
        return None
    return cl[i + days][1] / cl[i][1] - 1


# event queries
events = {
    "业绩预增/扭亏": "SELECT date, stock_code FROM announce WHERE title LIKE '%预增%' OR title LIKE '%扭亏%' OR (title LIKE '%业绩预告%' AND title LIKE '%增长%')",
    "业绩预减/首亏": "SELECT date, stock_code FROM announce WHERE title LIKE '%预减%' OR title LIKE '%首亏%' OR (title LIKE '%业绩预告%' AND title LIKE '%下降%')",
    "回购": "SELECT date, stock_code FROM announce WHERE title LIKE '%回购%'",
    "增持": "SELECT date, stock_code FROM announce WHERE title LIKE '%增持%'",
    "减持": "SELECT date, stock_code FROM announce WHERE title LIKE '%减持%'",
}
print("=== 公告事件后收益（T+1..T+10）===")
print(f"{'事件':<12} {'n':>5} {'平均10日收益%':>10} {'中位%':>8}")
for name, q in events.items():
    cur.execute(q)
    rows = cur.fetchall()
    rets = []
    for date, code in rows:
        d = str(date)[:10].replace("-", "")
        r = window_ret(code, d)
        if r is not None:
            rets.append(r)
    if not rets:
        print(f"{name:<12} {'0':>5}  -")
        continue
    avg = sum(rets) / len(rets) * 100
    rets.sort()
    med = rets[len(rets) // 2] * 100
    print(f"{name:<12} {len(rets):>5} {avg:>10.2f} {med:>8.2f}")

# market baseline: equal-weight 500-stock 10-day forward return in same period
import random
random.seed(7)
sample = random.sample([f for f in os.listdir(KT) if f.endswith("_daily_800.json")], 200)
base_rets = []
for f in sample:
    cl = []
    raw = json.load(open(os.path.join(KT, f), encoding="utf-8"))
    for r in raw:
        t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
        if t and r.get("c"):
            cl.append((t, float(r["c"])))
    cl.sort()
    for i in range(0, len(cl) - 10, 5):
        base_rets.append(cl[i + 10][1] / cl[i][1] - 1)
base_avg = sum(base_rets) / len(base_rets) * 100
print(f"\n全市场基线（200只抽样，10日收益）: 平均 {base_avg:.2f}%")
conn.close()
