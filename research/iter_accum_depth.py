# -*- coding: utf-8 -*-
"""Behavior-DNA refinement: accumulation depth/duration.
Does DEEPER accumulation (longer ACCUM, stronger volume contraction) boost event alpha?
ACCUM depth: 90d ret < -0.20 + vol contraction < 0.8 (deep) vs shallow."""
import glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()

code2file = {}
for f in os.listdir(KT):
    if f.endswith("_daily_800.json"):
        code2file[f.split("_")[0]] = os.path.join(KT, f)

bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []
            return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def accum_depth(bs, i):
    """Return depth level at bar i: DEEP / MID / SHALLOW / None(non-accum)."""
    if i < 91:
        return None
    w90 = bs[i - 90:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt = v20 / v90 if v90 else 1
    if ret90 < -0.20 and vt < 0.75:
        return "DEEP"
    if ret90 < -0.10 and vt < 0.9:
        return "MID"
    if ret90 < 0 and vt < 1.0:
        return "SHALLOW"
    return None


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
trades = []
seen = set()
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
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
    if i + 10 >= len(bs):
        continue
    depth = accum_depth(bs, i)
    if depth is None:
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    trades.append({"symbol": code, "entry_date": bs[i]["t"], "depth": depth,
                   "net_pnl_pct": round((bs[i + 10]["c"] / ep - 1) * 100 - 0.20, 4),
                   "t1_violation": "False"})
print("event trades with accum depth:", len(trades))
from collections import Counter
print("depth 分布:", dict(Counter(t["depth"] for t in trades)))


def report(label, rs):
    if len(rs) < 100:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 吸筹深度 × 事件 ===")
report("全部（ACCUM系）", trades)
report("深吸筹 DEEP", [t for t in trades if t["depth"] == "DEEP"])
report("中吸筹 MID", [t for t in trades if t["depth"] == "MID"])
report("浅吸筹 SHALLOW", [t for t in trades if t["depth"] == "SHALLOW"])
conn.close()
