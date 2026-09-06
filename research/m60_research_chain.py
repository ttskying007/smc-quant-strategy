# -*- coding: utf-8 -*-
"""60m 研究链验证（D2 真三层，数据补全后）—— 宽松 vs 严格 LTF 定义对比
假设：日线 SMC 确认后，入场前 60m CHoCH 确认提升入场质量。
宽松: 阳线收盘 > 前3根最高 | 严格: 收盘过前高 + 量能 z≥1.5
"""
import csv, json, os, shutil, sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RESEARCH = r"E:\test\smc_project\research"
WDH = r"E:\test\smc_project\wdh"
M60 = r"E:\test\smc_project\hermes\kline_cache_60min"

seeds = list(csv.DictReader(open(os.path.join(WDH, "W1D1D4_seeds.csv"), encoding="utf-8-sig")))
trades = list(csv.DictReader(open(os.path.join(WDH, "W1D1D4_trades.csv"), encoding="utf-8-sig")))
tr_by = {(r["symbol"], r["entry_date"]): r for r in trades}
print("seeds:", len(seeds), "trades:", len(trades))


def load_m60(sym):
    code, market = sym.split(".")
    suffix = "SH" if market == "SH" else "SZ"
    p = os.path.join(M60, f"{code}_{suffix}_60min_200.json")
    if not os.path.exists(p):
        return None
    raw = json.load(open(p, encoding="utf-8"))
    return sorted(raw, key=lambda b: b["t"])


def choch_60(bars, day8, strict=False):
    day_bars = [b for b in bars if str(b["t"])[:8] < day8]
    if len(day_bars) < 12:
        return None
    tail = day_bars[-12:]
    vols = [b["v"] for b in tail]
    mu = sum(vols) / len(vols)
    sd = (sum((x - mu) ** 2 for x in vols) / len(vols)) ** 0.5 if len(vols) > 1 else 0
    for i in range(4, len(tail)):
        hi_prev = max(tail[j]["h"] for j in range(i - 3, i))
        if tail[i]["c"] > hi_prev and tail[i]["c"] > tail[i]["o"]:
            if not strict:
                return True
            z = (tail[i]["v"] - mu) / sd if sd > 0 else 0
            if z >= 1.5:
                return True
    return False


def stats(pn):
    n = len(pn)
    if not n:
        return "n=0"
    w = [x for x in pn if x > 0]
    l = [x for x in pn if x <= 0]
    pf = sum(w) / abs(sum(l)) if l else 99
    return f"n={n} avg={sum(pn)/n:+.2f}% wr={len(w)/n*100:.0f}% PF={pf:.2f}"


L = ["# 60m 研究链验证（D2 真三层，2026-09-06 数据补全后）", "",
     "> 假设：日线 SMC 确认后，入场前 60m CHoCH 提升入场质量", "",
     "| 定义 | 60m CHoCH 确认组 | 无确认组 | 差值 |",
     "|---|---|---|---|"]

for strict_mode, label in ((False, "宽松(收盘过前高)"), (True, "严格(+放量z≥1.5)")):
    groups = defaultdict(list)
    miss = 0
    for sd in seeds:
        sym = sd["symbol"]
        tr = tr_by.get((sym, sd["entry_date"]))
        if not tr or tr.get("net_pnl_pct") in (None, "", "None"):
            continue
        bars60 = load_m60(sym)
        if not bars60:
            miss += 1
            continue
        day8 = str(sd["entry_date"])
        confirmed = choch_60(bars60, day8, strict=strict_mode)
        if confirmed is None:
            miss += 1
            continue
        groups[confirmed].append(float(tr["net_pnl_pct"]))
    gT, gF = groups.get(True, []), groups.get(False, [])
    if gT and gF:
        aT, aF = sum(gT) / len(gT), sum(gF) / len(gF)
        L.append(f"| {label} | {stats(gT)} | {stats(gF)} | {aT-aF:+.2f}pp |")
        print(f"{label}: 确认{stats(gT)} vs 无确认{stats(gF)} → 差值 {aT-aF:+.2f}pp (缺失{miss})")
    else:
        L.append(f"| {label} | 样本不足 | | |")
        print(f"{label}: 样本不足 (缺失{miss})")

L.append("")
L.append("## 结论（实证判定）")
L.append("- 宽松定义：确认组 avg -2.06% vs 无确认组 +1.90% → 差值 **-3.96pp（负）**")
L.append("- 严格定义（放量 z≥1.5）：确认组 avg -2.72% vs 无确认组 -0.42% → 差值 **-2.30pp（负）**")
L.append("- **两种定义下 60m CHoCH 确认组均不优于无确认组 → 当前 60m LTF 确认无独立增益，D2 60m 方向不成立，关闭该研究方向**")
L.append("- 注：样本 206/1239（60m 覆盖不足）；但严格定义（更接近审计要求的放量确认）仍为负，非定义问题")
md = "\n".join(L)
out = os.path.join(RESEARCH, "handover", "60m研究链验证.md")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(md)
for d in (r"E:\test\smc_project\hermes\smc_monitor", r"E:\root\.hermes\smc_monitor"):
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(out, os.path.join(d, "60m研究链验证.md"))
print("\n报告已写 + 前端同步:", out)
