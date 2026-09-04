# -*- coding: utf-8 -*-
"""Combo sensitivity: event hold period (5/10/15/20d) impact on yearly results.
Verifies combo robustness (not overfit to 10d hold)."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)

cache = {}
def bars_of(symbol):
    if symbol not in cache:
        p = code2file.get(symbol)
        if not p:
            cache[symbol] = None
            return None
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        cache[symbol] = bs
    return cache[symbol]


def event_trades(hold):
    out = []
    seen = set()
    for q in ["SELECT date, stock_code FROM announce WHERE title LIKE '%增持%'",
              "SELECT date, stock_code FROM announce WHERE title LIKE '%回购%'"]:
        cur.execute(q)
        for date, code in cur.fetchall():
            d = str(date)[:10].replace("-", "")
            if (code, d) in seen:
                continue
            seen.add((code, d))
            bs = bars_of(code)
            if not bs:
                continue
            dates = [b["t"] for b in bs]
            nxt = [x for x in dates if x > d]
            if not nxt:
                continue
            i = dates.index(nxt[0])
            if i + hold >= len(bs):
                continue
            ep = bs[i]["o"]
            if ep <= 0:
                continue
            out.append({"symbol": code, "entry_date": bs[i]["t"],
                        "net_pnl_pct": round((bs[i + hold]["c"] / ep - 1) * 100 - 0.20, 4),
                        "t1_violation": "False"})
    return out


def yearly(rows):
    by = defaultdict(list)
    for t in rows:
        by[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
    res = {}
    for y in ("2024", "2025", "2026"):
        rs = by.get(y, [])
        if rs:
            w = sum(1 for x in rs if x > 0)
            gp = sum(max(x, 0) for x in rs)
            gl = abs(sum(min(x, 0) for x in rs))
            res[y] = {"n": len(rs), "wr": round(100 * w / len(rs), 1),
                      "avg": round(sum(rs) / len(rs), 3), "pf": round(gp / gl, 2) if gl else 0}
    return res


print("=== 事件持有期敏感性（增持+回购）===")
for hold in (5, 10, 15, 20):
    trs = event_trades(hold)
    y = yearly(trs)
    print(f"\n持有 {hold} 日: n={len(trs)}")
    for yy in ("2024", "2025", "2026"):
        s = y.get(yy)
        if s:
            print(f"  {yy}: n={s['n']} WR={s['wr']}% avg={s['avg']:+.2f}% PF={s['pf']}")
conn.close()
