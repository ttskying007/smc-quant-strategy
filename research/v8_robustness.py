# -*- coding: utf-8 -*-
"""v8 robustness: behavior-stage threshold sensitivity.
Test if v8 results hold under threshold/window variations (anti-overfit check).
Variants: window 40/80, ret60 boundaries +/-0.05, vol_trend +/-0.1."""
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


def make_stage(win, acc_th, mark_th, dist_th, vt_acc, vt_mark, vt_dist):
    def stage_at(bs, i):
        if i < win + 1:
            return None
        w60 = bs[i - win:i]
        w20 = bs[i - 20:i]
        ret = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(b["v"] for b in w20) / len(w20)
        v60 = sum(b["v"] for b in w60) / len(w60)
        vt = v20 / v60 if v60 else 1
        if ret < acc_th and vt < vt_acc:
            return "ACCUM"
        if ret > dist_th and vt > vt_dist:
            return "DISTRIB"
        if ret > mark_th and vt > vt_mark:
            return "MARKUP"
        if ret > 0:
            return "UPTREND"
        return "DOWNTREND"
    return stage_at


def is_strong(title):
    t = str(title or "")
    if "回购" in t:
        if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
            return False
        return True
    if "增持" in t:
        return True
    return False


def build_events(stage_at, ev_stages):
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
        if i + 10 >= len(bs):
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        st = stage_at(bs, i)
        if st not in ev_stages:
            continue
        ev.append({"symbol": code, "entry_date": bs[i]["t"],
                   "net_pnl_pct": round((bs[i + 10]["c"] / ep - 1) * 100 - 0.20, 4), "src": "EVENT"})
    return ev


# load SMC leg once (UPTREND/MARKUP) - reuse stage from baseline def
BASE_STAGE = make_stage(60, -0.15, 0.20, 0.30, 0.9, 1.1, 1.3)
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

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


def build_smc(stage_at, smc_stages):
    out = []
    for t in trades:
        r20 = r20_of(t["symbol"], str(t["entry_date"]))
        if r20 is None or not (0 <= r20 < 0.15):
            continue
        code = t["symbol"].split(".")[0]
        bs = bars_of(code)
        dates = [b["t"] for b in bs]
        if str(t["entry_date"]) not in dates:
            prev = [d for d in dates if d < str(t["entry_date"])]
            if not prev:
                continue
            i = dates.index(prev[-1])
        else:
            i = dates.index(str(t["entry_date"]))
        st = stage_at(bs, i)
        if st in smc_stages:
            out.append(t)
    return out


def combo(ev, smc):
    combined = smc + ev
    for t in combined:
        t.setdefault("t1_violation", "False")
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(combined)
    o = gate["overall"]
    yrs = {y: [] for y in ("2024", "2025", "2026")}
    for t in combined:
        if t["year"] in yrs:
            yrs[t["year"]].append(t["net_pnl_pct"])
    line = f"n={o['n']} avg={o['avg']:+.2f}% PF={o['pf']} WR={o['wr']}%"
    for y in ("2024", "2025", "2026"):
        rs = yrs[y]
        if rs:
            line += f" | {y}:{sum(rs)/len(rs):+.2f}%"
    return line


print("=== v8 稳健性（阈值/窗口敏感性）===")
print("基线 (win=60, -0.15/0.20/0.30, vt 0.9/1.1/1.3):")
print("  ", combo(build_events(BASE_STAGE, ("ACCUM", "DOWNTREND")), build_smc(BASE_STAGE, ("UPTREND", "MARKUP"))))

variants = [
    ("窗口40", make_stage(40, -0.15, 0.20, 0.30, 0.9, 1.1, 1.3)),
    ("窗口80", make_stage(80, -0.15, 0.20, 0.30, 0.9, 1.1, 1.3)),
    ("边界+0.05", make_stage(60, -0.10, 0.25, 0.35, 0.9, 1.1, 1.3)),
    ("边界-0.05", make_stage(60, -0.20, 0.15, 0.25, 0.9, 1.1, 1.3)),
    ("量比+0.1", make_stage(60, -0.15, 0.20, 0.30, 1.0, 1.2, 1.4)),
    ("量比-0.1", make_stage(60, -0.15, 0.20, 0.30, 0.8, 1.0, 1.2)),
]
for name, stage in variants:
    evs = build_events(stage, ("ACCUM", "DOWNTREND"))
    smcs = build_smc(stage, ("UPTREND", "MARKUP"))
    print(f"{name}:")
    print("  ", combo(evs, smcs))
conn.close()
