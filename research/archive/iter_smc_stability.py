# -*- coding: utf-8 -*-
"""SMC 信号稳定性：确认后 BOS/CHOCH 在不同市场 regime（MA20 上/下行）的方向正确率
验证信号稳定性（定义在不同市场一致性）"""
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

files = sorted([f for f in os.listdir(KT) if f.endswith("_daily_800.json")])[:60]
stats = {"up": {"BOS": {"n": 0, "w": 0}, "CHOCH": {"n": 0, "w": 0}},
         "down": {"BOS": {"n": 0, "w": 0}, "CHOCH": {"n": 0, "w": 0}}}

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
        # regime: MA20 up/down at signal
        ma20 = sum(bars[k]["c"] for k in range(idx - 20, idx)) / 20
        reg = "up" if bars[idx]["c"] > ma20 else "down"
        # confirmation
        nb = bars[idx + 1]
        confirmed = (nb["c"] >= bars[idx]["c"] * 0.995) if direction == "bull" else (nb["c"] <= bars[idx]["c"] * 1.005)
        if not confirmed:
            continue
        c = bars[idx]["c"]
        c5 = bars[idx + 5]["c"]
        win = (c5 > c) if direction == "bull" else (c5 < c)
        stats[reg][typ]["n"] += 1
        if win:
            stats[reg][typ]["w"] += 1

print("=== 确认后信号稳定性（按 MA20 regime）===\n")
for reg, label in (("up", "上行(MA20↑)"), ("down", "下行(MA20↓)")):
    print(f"  {label}:")
    for typ in ("BOS", "CHOCH"):
        v = stats[reg][typ]
        if v["n"] > 0:
            print(f"    {typ}: n={v['n']} 正确率={100*v['w']/v['n']:.1f}%")
