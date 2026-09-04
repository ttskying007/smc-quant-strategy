# -*- coding: utf-8 -*-
"""Iteration 2: event + price-structure double confirmation.
Event (增持/回购) + stock in SMC bullish structure at entry (above 20d MA / rising).
Tests if adding a simple price-context filter improves event WR/avg."""
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


def get_all_events():
    cur.execute("SELECT date, stock_code FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
    out = []
    for date, code in cur.fetchall():
        out.append((str(date)[:10].replace("-", ""), code))
    return out


def structure_ok(bs, entry_idx):
    """price-structure confirmation at entry: close above 20d MA and MA rising."""
    if entry_idx < 20:
        return False
    closes = [bs[k]["c"] for k in range(entry_idx - 20, entry_idx)]
    ma20 = sum(closes) / 20
    ma20_prev = sum(closes[:-1]) / 19 if len(closes) > 1 else ma20
    return bs[entry_idx - 1]["c"] > ma20 and ma20 > ma20_prev


def run(filters, label, hold=10):
    events = get_all_events()
    trades = []
    seen = set()
    for d, code in events:
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
        if "struct" in filters and not structure_ok(bs, i):
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        trades.append({"symbol": code, "entry_date": bs[i]["t"],
                       "net_pnl_pct": round((bs[i + hold]["c"] / ep - 1) * 100 - 0.20, 4)})
    y = defaultdict(list)
    for t in trades:
        y[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
    print(f"\n{label}: n={len(trades)}")
    for yy in ("2024", "2025", "2026"):
        rs = y.get(yy, [])
        if rs:
            w = sum(1 for x in rs if x > 0)
            gp = sum(max(x, 0) for x in rs)
            gl = abs(sum(min(x, 0) for x in rs))
            print(f"  {yy}: n={len(rs)} WR={100*w/len(rs):.1f}% avg={sum(rs)/len(rs):+.2f}% PF={gp/gl if gl else 0:.2f}")


print("=== 事件 + 价格结构确认 ===")
run([], "事件（无过滤）")
run(["struct"], "事件 + 结构确认（>20MA且MA上升）")
conn.close()
