# -*- coding: utf-8 -*-
"""MSS 信号出场窗口：SMC 反转腿的最佳持有期（3/5/8/10/15 日）
MSS 78.5% 正确率 → 最优出场时间验证"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts\v25")
import smc_core_pine_like as pl

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

def load_bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
            out.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"]), "v": float(r["v"])})
    out.sort(key=lambda b: b["t"])
    return out


def detect_mss_bull(bs, i):
    if i < 5 or i + 3 >= len(bs):
        return None
    prev_lows = [bs[j]["l"] for j in range(i - 5, i)]
    if not prev_lows or bs[i]["l"] >= min(prev_lows):
        return None
    if bs[i + 1]["c"] <= bs[i - 1]["h"] and bs[i + 2]["c"] <= bs[i - 1]["h"]:
        return None
    if (max(bs[i + 1]["h"], bs[i + 2]["h"], bs[i + 3]["h"]) - bs[i]["l"]) / bs[i]["l"] < 0.015:
        return None
    return i


files = sorted([f for f in os.listdir(KT) if f.endswith("_daily_800.json")])[:120]
mss_list = []
for f in files:
    bars = load_bars(os.path.join(KT, f))
    if len(bars) < 400:
        continue
    for i in range(20, len(bars) - 16):
        if detect_mss_bull(bars, i) is not None:
            mss_list.append({"bs": bars, "i": i, "ep": bars[i]["c"]})
print("MSS bull 信号:", len(mss_list))

from collections import defaultdict
horizons = {3: [], 5: [], 8: [], 10: [], 15: []}
for m in mss_list:
    bs = m["bs"]
    i = m["i"]
    ep = m["ep"]
    for h in horizons:
        if i + h < len(bs):
            horizons[h].append((bs[i + h]["c"] / ep - 1) * 100)

print("\n=== MSS 信号出场窗口（持有期收益）===\n")
for h in (3, 5, 8, 10, 15):
    rs = horizons[h]
    if not rs:
        continue
    wins = [x for x in rs if x > 0]
    avg = sum(rs) / len(rs)
    print(f"  持有{h}日: n={len(rs)} avg={avg:+.2f}% 胜率={100*len(wins)/len(rs):.0f}% 中位={sorted(rs)[len(rs)//2]:+.2f}%")
