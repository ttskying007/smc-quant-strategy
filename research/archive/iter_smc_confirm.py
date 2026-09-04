# -*- coding: utf-8 -*-
"""BOS/CHOCH 确认机制优化：加 1-bar 确认（后续不 retrace）后准确性对比
验证优化方向（当前无确认 ≈50%，加确认应提升）"""
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

# more stocks for bigger sample
files = sorted([f for f in os.listdir(KT) if f.endswith("_daily_800.json")])[:40]

stats = {"BOS_raw": {"n": 0, "w": 0}, "BOS_conf": {"n": 0, "w": 0},
         "CHOCH_raw": {"n": 0, "w": 0}, "CHOCH_conf": {"n": 0, "w": 0}}

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
        if idx is None or idx + 7 >= len(bars):
            continue
        typ = s.get("type", "")
        if typ not in ("BOS", "CHOCH"):
            continue
        direction = s.get("direction", "")
        c = bars[idx]["c"]
        c5 = bars[idx + 5]["c"]
        win = (c5 > c) if direction == "bull" else (c5 < c)
        key = typ + "_raw"
        stats[key]["n"] += 1
        if win:
            stats[key]["w"] += 1
        # confirmation: next bar doesn't retrace beyond signal close
        nb = bars[idx + 1]
        if direction == "bull":
            confirmed = nb["c"] >= c * 0.995  # next close holds
        else:
            confirmed = nb["c"] <= c * 1.005
        if confirmed:
            keyc = typ + "_conf"
            stats[keyc]["n"] += 1
            if win:
                stats[keyc]["w"] += 1

print("=== BOS/CHOCH 确认机制对比（40 只股票）===\n")
for k in ("BOS_raw", "BOS_conf", "CHOCH_raw", "CHOCH_conf"):
    v = stats[k]
    if v["n"] > 0:
        print(f"  {k}: n={v['n']} 方向正确率={100*v['w']/v['n']:.1f}%")
