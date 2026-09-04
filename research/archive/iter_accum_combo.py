# -*- coding: utf-8 -*-
"""ACCUM 整合组合级验证：事件腿 ACCUM 优先 + 延续腿 → 组合 Top50%
（在 v20c 组合框架内测 ACCUM 排序的完整影响）"""
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


def stage_of(bs, i):
    if i < 91:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(b["v"] for b in bs[i - 20:i]) / 20
    v60 = sum(b["v"] for b in bs[i - 60:i]) / 60
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


# load v20c trades + enrich event stage
trades = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

# enrich EVENT trades with stage (ACCUM priority)
for t in trades:
    if t.get("src") != "EVENT":
        t["stage"] = ""
        continue
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        t["stage"] = ""
        continue
    dates = [b["t"] for b in bs]
    if ed not in dates:
        prev = [d for d in dates if d < ed]
        if not prev:
            t["stage"] = ""
            continue
        i = dates.index(prev[-1])
    else:
        i = dates.index(ed)
    t["stage"] = stage_of(bs, i) or ""


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


def score(t):
    """0/1: ACCUM stage priority for EVENT; low-vol for CONT."""
    if t.get("src") == "EVENT":
        return 1 if t.get("stage") == "ACCUM" else 0
    if t.get("src") == "CONT":
        return 1  # already low-vol filtered
    return 0


scored = sorted(trades, key=lambda t: score(t), reverse=True)
n = len(scored)
print("\n=== 组合级 ACCUM 排序 ===")
report("全量", trades)
report("Top50% ACCUM优先(组合)", [dict(t) for t in scored[:n // 2]])
# 2026-strong check
report("ACCUM事件子集", [t for t in trades if t.get("src") == "EVENT" and t.get("stage") == "ACCUM"])
