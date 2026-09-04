# -*- coding: utf-8 -*-
"""SMC 信号定义准确性验证：BOS/CHOCH/sweep 信号后 1/3/5 日价格行为
信号方向是否正确预示后续走势（定义准确性 + 稳定性）"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts\v25")
sys.path.insert(0, r"E:\test\smc_project\hermes\scripts")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# use pine_like signal detection (current kline source)
import smc_core_pine_like as pl

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

# test on 5 representative stocks
tests = ["000651_SZ", "000404_SZ", "600519_SH", "300750_SZ", "603038_SH"]
all_stats = {"BOS": {"n": 0, "win5": 0}, "CHOCH": {"n": 0, "win5": 0},
             "SWEEP_bull": {"n": 0, "win5": 0}, "SWEEP_bear": {"n": 0, "win5": 0}}

for name in tests:
    p = os.path.join(KT, name + "_daily_800.json")
    if not os.path.exists(p):
        continue
    bars = load_bars(p)
    if len(bars) < 200:
        continue
    try:
        res = pl.detect_all_signals_pine_like(bars)
        sigs = res["signals"]
    except Exception as e:
        print(f"{name}: detect FAIL {e}")
        continue
    # analyze signal accuracy
    for s in sigs.get("swing_structure", []):
        idx = s.get("index")
        if idx is None or idx + 6 >= len(bars):
            continue
        typ = s.get("type", "")
        c = bars[idx]["c"]
        c5 = bars[idx + 5]["c"]
        if typ in ("BOS", "CHOCH"):
            # signal direction: bull if close break high, bear if break low
            direction = s.get("direction", "")
            if direction == "bull":
                win = c5 > c
            else:
                win = c5 < c
            all_stats[typ]["n"] += 1
            if win:
                all_stats[typ]["win5"] += 1
    for s in sigs.get("sweeps", []):
        idx = s.get("index")
        if idx is None or idx + 6 >= len(bars):
            continue
        direction = s.get("direction", "")
        c = bars[idx]["c"]
        c5 = bars[idx + 5]["c"]
        key = "SWEEP_bull" if direction == "bull" else "SWEEP_bear"
        win = c5 > c if direction == "bull" else c5 < c
        all_stats[key]["n"] += 1
        if win:
            all_stats[key]["win5"] += 1

print("=== SMC 信号定义准确性（信号后 5 日方向正确率）===\n")
for k, v in all_stats.items():
    if v["n"] > 0:
        print(f"  {k}: n={v['n']} 方向正确率={100*v['win5']/v['n']:.1f}%")
