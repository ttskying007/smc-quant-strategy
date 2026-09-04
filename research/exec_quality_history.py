# -*- coding: utf-8 -*-
"""Historical version execution-quality comparison (user: audit ALL good versions).
For each version's trades (v8/v10/v13/v16b), analyze entry/exit quality:
- entry: open vs POI/prev-close, day-low diff
- exit: 10d/20d close vs subsequent peak (sold early?)
Versions differ in event hold (v8/10: 10d, v13+: depth-dependent) and filters."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

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


def audit_trades(trades, label):
    """For each trade, entry vs prev-close gap, entry-day low, exit vs peak."""
    stats = {"n": 0, "gap": [], "day_low": [], "exit_vs_peak": []}
    for t in trades:
        code = str(t.get("symbol", "")).split(".")[0]
        ed = str(t.get("entry_date", ""))
        hold = int(t.get("hold", 10))
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
        if i == 0 or i + hold + 5 >= len(bs):
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        stats["n"] += 1
        stats["gap"].append((ep / bs[i - 1]["c"] - 1) * 100)
        stats["day_low"].append((bs[i]["l"] / ep - 1) * 100)
        ex = bs[i + hold]["c"]
        stats["exit_vs_peak"].append((max(bs[k]["h"] for k in range(i + hold + 1, min(len(bs), i + hold + 6))) / ex - 1) * 100)
    print(f"=== {label} 执行质量（n={stats['n']}）===")
    print(f"  入场跳空 med: {med(stats['gap']):+.2f}% | 入场日低点 med: {med(stats['day_low']):+.2f}% | 平仓后5日峰值 med: {med(stats['exit_vs_peak']):+.2f}%")
    return stats


# load each version's trades
versions = {
    "v8 (事件10日全量)": r"E:\test\smc_project\research\combo_v8_trades.csv",
    "v10 (深度依赖持有)": r"E:\test\smc_project\research\combo_v10_trades.csv",
    "v13 (ADX互补)": r"E:\test\smc_project\research\combo_v13_trades.csv",
    "v16b (生产, SMC+FVG+事件趋势)": r"E:\test\smc_project\research\combo_v15_trades.csv",
}
for label, path in versions.items():
    if not os.path.exists(path):
        print(f"=== {label}: 文件缺失 ===")
        continue
    trades = []
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r.get("src") == "EVENT":
                trades.append(r)
    audit_trades(trades, label)
    print()
