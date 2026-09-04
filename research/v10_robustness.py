# -*- coding: utf-8 -*-
"""v10 robustness: depth-hold sensitivity.
Vary DEEP thresholds and DEEP hold (15/20/25) - check yearly stays positive."""
import csv, glob, io, json, os, sqlite3, sys
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


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def get_events(ret_th, vt_th, hold_deep, hold_std, stage_keep=("ACCUM", "DOWNTREND")):
    """Return event trades under given deep-threshold + hold policy."""
    ev = []
    seen = set()
    cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
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
        if i < 91:
            continue
        w90 = bs[i - 90:i]
        w60 = bs[i - 60:i]
        w20 = bs[i - 20:i]
        ret90 = w90[-1]["c"] / w90[0]["c"] - 1
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(b["v"] for b in w20) / len(w20)
        v60 = sum(b["v"] for b in w60) / len(w60)
        v90 = sum(b["v"] for b in w90) / len(w90)
        vt60 = v20 / v60 if v60 else 1
        vt90 = v20 / v90 if v90 else 1
        if ret60 < -0.15 and vt60 < 0.9:
            st = "ACCUM"
        elif ret60 > 0.30 and vt60 > 1.3:
            st = "DISTRIB"
        elif ret60 > 0.20 and vt60 > 1.1:
            st = "MARKUP"
        elif ret60 > 0:
            st = "UPTREND"
        else:
            st = "DOWNTREND"
        if st not in stage_keep:
            continue
        deep = ret90 < ret_th and vt90 < vt_th
        hold = hold_deep if deep else hold_std
        if i + hold >= len(bs):
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        ev.append({"symbol": code, "entry_date": bs[i]["t"],
                   "net_pnl_pct": round((bs[i + hold]["c"] / ep - 1) * 100 - 0.20, 4),
                   "t1_violation": "False"})
    return ev


def combo_report(ev):
    if len(ev) < 500:
        print(f"  events n={len(ev)} (过小)")
        return None
    for t in ev:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(ev)
    o = gate["overall"]
    line = f"n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']} WR={o['wr']}%"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in ev if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    return line


print("=== v10 稳健性（深度阈值 + 持有期）===")
variants = [
    ("基线 (-0.20,0.75, D20/S10)", -0.20, 0.75, 20, 10),
    ("DEEP 15日 (D15/S10)", -0.20, 0.75, 15, 10),
    ("DEEP 25日 (D25/S10)", -0.20, 0.75, 25, 10),
    ("宽松深度 (D20, -0.15,0.85)", -0.15, 0.85, 20, 10),
    ("严格深度 (D20, -0.25,0.65)", -0.25, 0.65, 20, 10),
    ("深度也10日 (D10/S10)", -0.20, 0.75, 10, 10),
]
for label, rt, vt, dh, sh in variants:
    ev = get_events(rt, vt, dh, sh)
    line = combo_report(ev)
    print(f"  {label}: {line}")
conn.close()
