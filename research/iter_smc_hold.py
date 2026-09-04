# -*- coding: utf-8 -*-
"""SMC hold-period x behavior stage: UPTREND/MARKUP signals - longer hold for trend?
Tests if SMC leg (TP2-R20) in markup stages benefits from extended hold."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def stage_at(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    if ret60 > 0:
        return "UPTREND"
    return "DOWNTREND"


# load TP2 tencent trades
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# r20 filter
closes_cache = {}
def r20_of(symbol, entry_date):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in closes_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            closes_cache[fn] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        cl = [(("".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]), float(r["c"])) for r in raw if r.get("t") and r.get("c")]
        cl.sort()
        closes_cache[fn] = cl
    cl = closes_cache[fn]
    ds = [c[0] for c in cl]
    if entry_date not in ds:
        prev = [d for d in ds if d < entry_date]
        if not prev:
            return None
        i = ds.index(prev[-1])
    else:
        i = ds.index(entry_date) - 1
    if i < 20:
        return None
    return cl[i][1] / cl[i - 20][1] - 1

# forward pnl at different holds
bar_cache = {}
def fwd(symbol, entry_date, hold):
    code, ex = symbol.split(".")
    fn = f"{code}_{ex}_daily_800.json"
    if fn not in bar_cache:
        p = os.path.join(KT, fn)
        if not os.path.exists(p):
            bar_cache[fn] = None
            return None
        bar_cache[fn] = bars(p)
    bs = bar_cache[fn]
    if not bs:
        return None
    dates = [b["t"] for b in bs]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date)
    if i + hold >= len(bs):
        return None
    ep = bs[i]["o"]
    if ep <= 0:
        return None
    return (bs[i + hold]["c"] / ep - 1) * 100 - 0.20


rows = []
for t in trades:
    r20 = r20_of(t["symbol"], str(t["entry_date"]))
    if r20 is None or not (0 <= r20 < 0.15):
        continue
    code, ex = t["symbol"].split(".")
    fn = f"{code}_{ex}_daily_800.json"
    bs = bars(os.path.join(KT, fn))
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    ed = str(t["entry_date"])
    i = dates.index(ed) if ed in dates else None
    if i is None:
        prev = [d for d in dates if d < ed]
        if not prev:
            continue
        i = dates.index(prev[-1])
    st = stage_at(bs, i)
    if st not in ("UPTREND", "MARKUP"):
        continue
    for h in (5, 10, 15, 20):
        if i + h >= len(bs):
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        p = (bs[i + h]["c"] / ep - 1) * 100 - 0.20
        rows.append({"stage": st, "hold": h, "pnl": p, "entry_date": ed})
print("SMC markup rows:", len(rows))

print("\n=== SMC 行为阶段 × 持有期 ===")
for st in ("UPTREND", "MARKUP"):
    for h in (5, 10, 15, 20):
        rs = [r for r in rows if r["stage"] == st and r["hold"] == h]
        if len(rs) < 40:
            continue
        avg = sum(r["pnl"] for r in rs) / len(rs)
        w = sum(1 for r in rs if r["pnl"] > 0)
        by_y = defaultdict(list)
        for r in rs:
            by_y[str(r["entry_date"])[:4]].append(r["pnl"])
        ys = " ".join(f"{y}:{sum(v)/len(v):+.1f}" for y, v in sorted(by_y.items()) if len(v) >= 15)
        print(f"  {st} hold={h}: n={len(rs)} WR={100*w/len(rs):.0f}% avg={avg:+.2f}% | {ys}")
