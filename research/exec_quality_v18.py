# -*- coding: utf-8 -*-
"""v18 execution quality audit (per user: every iteration)."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]


def med(vals):
    if not vals:
        return None
    s = sorted(vals)
    return s[len(s) // 2]


trades = []
with open(r"E:\test\smc_project\research\combo_v18_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)

# event leg audit (majority)
ev = [t for t in trades if t.get("src") == "EVENT"]
smc = [t for t in trades if t.get("src") != "EVENT"]
print(f"total {len(trades)} | event {len(ev)} | smc {len(smc)}")

# event leg
estats = {"n": 0, "gap": [], "day_low": [], "exit_vs_peak": []}
for t in ev:
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if ed not in dates:
        prev = [d for d in dates if d < ed]
        if not prev:
            continue
        i = dates.index(prev[-1])
    else:
        i = dates.index(ed)
    if i == 0 or i + 15 + 5 >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    estats["n"] += 1
    estats["gap"].append((ep / bs[i - 1]["c"] - 1) * 100)
    estats["day_low"].append((bs[i]["l"] / ep - 1) * 100)
    ex = bs[i + 15]["c"]
    estats["exit_vs_peak"].append((max(bs[k]["h"] for k in range(i + 16, min(len(bs), i + 21))) / ex - 1) * 100)

print(f"\n=== v18 事件腿执行质量（n={estats['n']}）===")
print(f"  入场跳空 med: {med(estats['gap']):+.2f}%")
print(f"  入场日低点 med: {med(estats['day_low']):+.2f}%（负=买早，T+1固有）")
print(f"  平仓后5日峰值 med: {med(estats['exit_vs_peak']):+.2f}%（正=卖早，结构性趋势）")

# SMC leg
sstats = {"n": 0, "day_low": [], "exit_vs_peak": []}
for t in smc:
    code = str(t.get("symbol", "")).split(".")[0]
    ed = str(t.get("entry_date", ""))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if ed not in dates:
        prev = [d for d in dates if d < ed]
        if not prev:
            continue
        i = dates.index(prev[-1])
    else:
        i = dates.index(ed)
    if i == 0 or i + 10 + 5 >= len(bs):
        continue
    ep = bs[i]["o"]
    if ep <= 0:
        continue
    sstats["n"] += 1
    sstats["day_low"].append((bs[i]["l"] / ep - 1) * 100)
    # SMC holds ~ up to 40d; use 10d close as reference for peak check
    ex = bs[i + 10]["c"]
    sstats["exit_vs_peak"].append((max(bs[k]["h"] for k in range(i + 11, min(len(bs), i + 16))) / ex - 1) * 100)

print(f"\n=== v18 SMC 腿执行质量（n={sstats['n']}）===")
print(f"  入场日低点 med: {med(sstats['day_low']):+.2f}%")
print(f"  10日参考后5日峰值 med: {med(sstats['exit_vs_peak']):+.2f}%")
