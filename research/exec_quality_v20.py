# -*- coding: utf-8 -*-
"""v20 执行质量审计（每轮必做）：反转腿（15/20日）+ 延续腿（10日）"""
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
with open(r"E:\test\smc_project\research\combo_v20_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)

# by src: EVENT (reversal), SMC (reversal), CONT (continuation)
ev = [t for t in trades if t.get("src") == "EVENT"]
cont = [t for t in trades if t.get("src") == "CONT"]
print(f"total {len(trades)} | EVENT {len(ev)} | CONT {len(cont)}")


def audit(label, pool, hold_ref):
    stats = {"n": 0, "gap": [], "day_low": [], "exit_vs_peak": []}
    for t in pool:
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
        if i == 0 or i + hold_ref + 5 >= len(bs):
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        stats["n"] += 1
        stats["gap"].append((ep / bs[i - 1]["c"] - 1) * 100)
        stats["day_low"].append((bs[i]["l"] / ep - 1) * 100)
        ex = bs[i + hold_ref]["c"]
        stats["exit_vs_peak"].append((max(bs[k]["h"] for k in range(i + hold_ref + 1, min(len(bs), i + hold_ref + 6))) / ex - 1) * 100)
    print(f"=== {label}（n={stats['n']}）===")
    print(f"  入场跳空 med: {med(stats['gap']):+.2f}%")
    print(f"  入场日低点 med: {med(stats['day_low']):+.2f}%（负=买早）")
    print(f"  平仓后5日峰值 med: {med(stats['exit_vs_peak']):+.2f}%（正=卖早）")


print("\n")
audit("v20 反转腿（事件，15日参考）", ev, 15)
audit("v20 延续腿（CONT，10日参考）", cont, 10)
