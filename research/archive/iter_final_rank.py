# -*- coding: utf-8 -*-
"""组合精选最终确认：简单排序(DEEP+高波/FVG/低波动) vs rank_score 排序（事件腿）
确认实盘精选方案的最终选择"""
import csv, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
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


def stage_and_info(bs, i):
    if i < 91:
        return None, False, 0
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / 20
    v60 = sum(b["v"] for b in w60) / 60
    v90 = sum(b["v"] for b in w90) / 90
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
    if ret60 < -0.15 and vt60 < 0.9:
        return "ACCUM", deep, vol20
    if ret60 > 0.30 and vt60 > 1.3:
        return "DISTRIB", deep, vol20
    if ret60 > 0.20 and vt60 > 1.1:
        return "MARKUP", deep, vol20
    return ("UPTREND" if ret60 > 0 else "DOWNTREND"), deep, vol20


trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# enrich EVENT with stage/deep/vol20
for t in trades:
    if t.get("src") != "EVENT":
        t["simple"] = 0  # CONT keep via low-vol (already)
        t["rank"] = 0
        continue
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        t["simple"] = t["rank"] = 0
        continue
    dates = [b["t"] for b in bs]
    if ed not in dates:
        prev = [d for d in dates if d < ed]
        if not prev:
            t["simple"] = t["rank"] = 0
            continue
        i = dates.index(prev[-1])
    else:
        i = dates.index(ed)
    st, deep, vol20 = stage_and_info(bs, i)
    # simple sort: DEEP + high vol
    t["simple"] = (2 if deep else 0) + (1 if vol20 > 0.041 else 0)
    # rank score: ACCUM + vol
    avg_v = sum(bs[k]["v"] for k in range(i + 1 - 20, i + 1)) / 20 if i + 1 >= 20 else 0
    v_ratio = bs[i + 1]["v"] / avg_v if (avg_v and i + 1 < len(bs)) else 1.0
    t["rank"] = (2 if st == "ACCUM" else 1) + (1 if v_ratio > 1.2 else 0)


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t.setdefault("t1_violation", "False")
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


n = len(trades)
simple_sorted = sorted(trades, key=lambda t: -t.get("simple", 0))
rank_sorted = sorted(trades, key=lambda t: -t.get("rank", 0))
print("=== 组合精选最终确认 ===")
report("全量", trades)
report("Top50% 简单排序", [dict(t) for t in simple_sorted[:n // 2]])
report("Top50% rank_score", [dict(t) for t in rank_sorted[:n // 2]])
report("Top40% 简单排序", [dict(t) for t in simple_sorted[:int(n * 0.4)]])
report("Top40% rank_score", [dict(t) for t in rank_sorted[:int(n * 0.4)]])
