# -*- coding: utf-8 -*-
"""SMC 信号大样本验证：全市场样本（BOS/CHOCH 确认后准确性 + 收益分布）
用 150 只股票验证信号定义的统计稳定性"""
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
stats = {"BOS": {"n": 0, "w": 0, "pnl3": []}, "CHOCH": {"n": 0, "w": 0, "pnl3": []}}

for f in files:
    bars = load_bars(os.path.join(KT, f))
    if len(bars) < 300:
        continue
    try:
        res = pl.detect_all_signals_pine_like(bars)
        sigs = res["signals"]
    except Exception:
        continue
    for s in sigs.get("swing_structure", []):
        idx = s.get("index")
        if idx is None or idx + 7 >= len(bars) or idx < 21:
            continue
        typ = s.get("type", "")
        if typ not in ("BOS", "CHOCH"):
            continue
        direction = s.get("direction", "")
        nb = bars[idx + 1]
        confirmed = (nb["c"] >= bars[idx]["c"] * 0.995) if direction == "bull" else (nb["c"] <= bars[idx]["c"] * 1.005)
        if not confirmed:
            continue
        c = bars[idx]["c"]
        c5 = bars[idx + 5]["c"]
        win = (c5 > c) if direction == "bull" else (c5 < c)
        stats[typ]["n"] += 1
        if win:
            stats[typ]["w"] += 1
        stats[typ]["pnl3"].append((c5 / c - 1) * 100 if direction == "bull" else (1 - c5 / c) * 100)

print("=== SMC 信号大样本验证（150 只股票，确认后）===\n")
for k, v in stats.items():
    if v["n"] > 0:
        pnl = sorted(v["pnl3"])
        n = len(pnl)
        print(f"  {k}: n={v['n']} 方向正确率={100*v['w']/v['n']:.1f}%")
        print(f"    5日方向收益: 中位={pnl[n//2]:+.2f}% P25={pnl[n//4]:+.2f}% P75={pnl[3*n//4]:+.2f}%")
