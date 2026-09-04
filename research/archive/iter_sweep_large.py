# -*- coding: utf-8 -*-
"""Sweep 信号大样本验证：SSL扫损方向正确率 + 收益分布
之前样本不足（5+5），用 150 只股票大样本深入"""
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

files = sorted([f for f in os.listdir(KT) if f.endswith("_daily_800.json")])[:150]
stats = {"SWEEP_bull": {"n": 0, "w": 0, "pnl5": []}, "SWEEP_bear": {"n": 0, "w": 0, "pnl5": []}}

for f in files:
    bars = load_bars(os.path.join(KT, f))
    if len(bars) < 300:
        continue
    try:
        res = pl.detect_all_signals_pine_like(bars)
        sigs = res["signals"]
    except Exception:
        continue
    for s in sigs.get("sweeps", []):
        idx = s.get("index")
        if idx is None or idx + 7 >= len(bars) or idx < 21:
            continue
        direction = s.get("direction", "")
        # check if it's a real sweep (SSL low breached then recovered)
        c = bars[idx]["c"]
        c5 = bars[idx + 5]["c"]
        key = "SWEEP_bull" if direction == "bull" else "SWEEP_bear"
        win = (c5 > c) if direction == "bull" else (c5 < c)
        stats[key]["n"] += 1
        if win:
            stats[key]["w"] += 1
        stats[key]["pnl5"].append((c5 / c - 1) * 100 if direction == "bull" else (1 - c5 / c) * 100)

print("=== Sweep 信号大样本验证（150 只股票）===\n")
for k, v in stats.items():
    if v["n"] > 0:
        pnl = sorted(v["pnl5"])
        n = len(pnl)
        print(f"  {k}: n={v['n']} 方向正确率={100*v['w']/v['n']:.1f}%")
        print(f"    5日方向收益: 中位={pnl[n//2]:+.2f}% P25={pnl[n//4]:+.2f}% P75={pnl[3*n//4]:+.2f}%")