# -*- coding: utf-8 -*-
"""组合级排序精选：三腿统一质量分数（实盘小资金方案）
事件：DEEP+高波动=高分；SMC：FVG多=高分；延续：低波动=高分
按分数取 Top N 看组合表现（精选 vs 全量）"""
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

# compute quality features per trade (recompute from klines)
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


def score_trade(t):
    """Unified quality score: EVENT deep+vol / SMC fvg / CONT low-vol."""
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
    if i < 90:
        return 0.0
    src = t.get("src", "")
    if src == "EVENT":
        w90 = bs[i - 90:i]
        w20 = bs[i - 20:i]
        ret90 = w90[-1]["c"] / w90[0]["c"] - 1
        v20 = sum(b["v"] for b in w20) / 20
        v90 = sum(b["v"] for b in w90) / 90
        deep = ret90 < -0.20 and (v20 / v90 if v90 else 1) < 0.75
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        return (2 if deep else 0) + (1 if vol20 > 0.041 else 0)
    if src == "CONT":
        w20 = bs[i - 20:i]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20
        return 1 if vol20 < 0.041 else 0
    # SMC
    fvg_cnt = sum(1 for k in range(max(3, i - 12), i) if bs[k]["h"] < bs[k - 2]["l"])
    return fvg_cnt


scored = []
for t in trades:
    s = score_trade(t)
    scored.append((t, s))

scored.sort(key=lambda x: x[1], reverse=True)


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


print("\n=== 组合级排序精选 ===")
report("全量（v20c）", [t for t, s in scored])
n = len(scored)
for pct in (0.5, 0.3, 0.2):
    top = [dict(t) for t, s in scored[:int(n * pct)]]
    report(f"Top{pct*100:.0f}%（精选）", top)
