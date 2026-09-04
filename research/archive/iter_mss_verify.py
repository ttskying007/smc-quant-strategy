# -*- coding: utf-8 -*-
"""MSS（Market Structure Shift）组合信号验证：sweep + CHOCH + 位移
验证 SMC 反转腿核心信号的准确性（单独 sweep ≈50%，MSS 组合应显著提升）"""
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

# MSS simulation: sweep low + next 2 bars close above sweep low + displacement (close > recent swing high area)
def detect_mss_bull(bs, i):
    if i < 5 or i + 3 >= len(bs):
        return None
    # sweep: bar i low < previous 5 lows
    prev_lows = [bs[j]["l"] for j in range(i - 5, i)]
    if not prev_lows or bs[i]["l"] >= min(prev_lows):
        return None
    # CHOCH: bars i+1/i+2 close above bar i-1 high (structure shift)
    if bs[i + 1]["c"] <= bs[i - 1]["h"] and bs[i + 2]["c"] <= bs[i - 1]["h"]:
        return None
    # displacement: move up > 1.5% within 3 bars
    if (max(bs[i + 1]["h"], bs[i + 2]["h"], bs[i + 3]["h"]) - bs[i]["l"]) / bs[i]["l"] < 0.015:
        return None
    return i

files = sorted([f for f in os.listdir(KT) if f.endswith("_daily_800.json")])[:150]
mss = {"bull": {"n": 0, "w": 0, "pnl5": []}, "bear": {"n": 0, "w": 0, "pnl5": []}}

for f in files:
    bars = load_bars(os.path.join(KT, f))
    if len(bars) < 300:
        continue
    for i in range(20, len(bars) - 6):
        # bull MSS
        if detect_mss_bull(bars, i) is not None:
            c = bars[i]["c"]
            c5 = bars[i + 5]["c"]
            mss["bull"]["n"] += 1
            if c5 > c:
                mss["bull"]["w"] += 1
            mss["bull"]["pnl5"].append((c5 / c - 1) * 100)

print("=== MSS 组合信号验证（150 只股票，bull）===\n")
v = mss["bull"]
if v["n"] > 0:
    pnl = sorted(v["pnl5"])
    n = len(pnl)
    print(f"  MSS_bull: n={v['n']} 方向正确率={100*v['w']/v['n']:.1f}%")
    print(f"    5日收益: 中位={pnl[n//2]:+.2f}% P25={pnl[n//4]:+.2f}% P75={pnl[3*n//4]:+.2f}%")
    wins = [x for x in pnl if x > 0]
    print(f"    正收益占比: {100*len(wins)/n:.0f}%")
