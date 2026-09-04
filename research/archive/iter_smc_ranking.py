# -*- coding: utf-8 -*-
"""SMC leg ranking: quality features for capital allocation.
Rank SMC trades by (r20 position - closer to 0.15 = more room, FVG count, stage strength).
Test top-K SMC performance (like event ranking)."""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c, v = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c")), we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


bar_cache = {}
def get_bars(sym):
    if sym not in bar_cache:
        bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
    return bar_cache[sym]


rows = []
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for sd in we.build_seeds(sym, daily):
        r20 = sd.get("r20")
        if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
            continue
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        w60 = daily[entry_idx - 60:entry_idx]
        w20 = daily[entry_idx - 20:entry_idx]
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(x["v"] for x in w20) / len(w20)
        v60 = sum(x["v"] for x in w60) / len(w60)
        vt = v20 / v60 if v60 else 1
        if ret60 < -0.15 and vt < 0.9:
            st = "ACCUM"
        elif ret60 > 0.30 and vt > 1.3:
            st = "DISTRIB"
        elif ret60 > 0.20 and vt > 1.1:
            st = "MARKUP"
        elif ret60 > 0:
            st = "UPTREND"
        else:
            st = "DOWNTREND"
        if st not in ("UPTREND", "MARKUP"):
            continue
        # FVG count (more bearish FVG = more exhausted supply)
        fvg_cnt = sum(1 for k in range(max(3, entry_idx - 12), entry_idx) if daily[k]["h"] < daily[k - 2]["l"])
        # VWAP dev
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vw = pv / vol if vol else 0
        dev = (daily[entry_idx]["c"] - vw) / vw if vw else 0
        if dev < 0.05:
            continue
        tr = we.replay_tp2(sd, daily)
        if not tr:
            continue
        r20v = float(r20)
        rows.append({"symbol": sym, "entry_date": tr["entry_date"], "net_pnl_pct": tr["net_pnl_pct"],
                     "r20": r20v, "fvg_cnt": fvg_cnt, "dev": dev, "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files", flush=True)
print(f"SMC rows: {len(rows)}")


def report(label, rs):
    if len(rs) < 30:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']} WR={o['wr']}%")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== SMC 腿排序（r20 位置：更接近 0.15 = 更多空间）===")
report("全部 SMC", rows)
# r20 position: lower r20 = more room (fresher start)
rows.sort(key=lambda r: r["r20"])
n70 = max(30, int(len(rows) * 0.7))
report("Top70% r20 低（更新鲜）", rows[:n70])
report("Top50% r20 低", rows[:max(30, int(len(rows) * 0.5))])
# fvg count ranking
rows2 = sorted(rows, key=lambda r: r["fvg_cnt"], reverse=True)
report("Top70% FVG 多（抛压更尽）", rows2[:n70])
report("Top50% FVG 多", rows2[:max(30, int(len(rows) * 0.5))])
