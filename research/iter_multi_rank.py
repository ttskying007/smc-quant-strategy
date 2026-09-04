# -*- coding: utf-8 -*-
"""多维统一排序：组合精选加全质量特征（事件放量/MSS/量能）→ Top50% 是否更强"""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

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


def score_full(t):
    """Multi-feature score per leg."""
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        return 0.0
    dates = [b["t"] for b in bs]
    if ed not in dates:
        prev = [d for d in dates if d < ed]
        if not prev:
            return 0.0
        i = dates.index(prev[-1])
    else:
        i = dates.index(ed)
    if i < 91:
        return 0.0
    src = t.get("src", "")
    s = 0.0
    if src == "EVENT":
        w90 = bs[i - 90:i]
        w20 = bs[i - 20:i]
        ret90 = w90[-1]["c"] / w90[0]["c"] - 1
        v20 = sum(b["v"] for b in w20) / 20
        v90 = sum(b["v"] for b in w90) / 90
        deep = ret90 < -0.20 and (v20 / v90 if v90 else 1) < 0.75
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        # entry-day volume ratio
        avg_v = sum(bs[k]["v"] for k in range(i - 20, i)) / 20
        v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1
        s = (2 if deep else 0) + (1 if vol20 > 0.041 else 0) + (2 if v_ratio > 1.2 else 0)
    elif src == "CONT":
        w20 = bs[i - 20:i]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        hi10 = max(bs[k]["h"] for k in range(i - 10, i))
        mss = 1 if bs[i]["c"] > hi10 else 0
        s = (2 if vol20 < 0.041 else 0) + (1 if mss else 0)
    else:
        fvg_cnt = sum(1 for k in range(max(3, i - 12), i) if bs[k]["h"] < bs[k - 2]["l"])
        avg_v = sum(bs[k]["v"] for k in range(i - 20, i)) / 20
        v_ratio = bs[i]["v"] / avg_v if avg_v > 0 else 1
        s = fvg_cnt + (1 if 0.8 <= v_ratio <= 1.2 else 0)
    return s


scored = sorted([(t, score_full(t)) for t in trades], key=lambda x: x[1], reverse=True)
print("多维评分完成:", len(scored))


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


print("\n=== 多维排序精选（全特征）===")
report("全量", [t for t, s in scored])
n = len(scored)
report("Top50% 多维", [dict(t) for t, s in scored[:n // 2]])
report("Top40% 多维", [dict(t) for t, s in scored[:int(n * 0.4)]])
