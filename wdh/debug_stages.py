# -*- coding: utf-8 -*-
import io, json, os, sys
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

sym = "600519_SH"
p = os.path.join(r"E:\test\smc_project\hermes\kline_cache", f"{sym}_daily_750.json")
daily = we.bars_for(p)
weekly = we.aggregate_weekly(daily)
print(f"daily={len(daily)} weekly={len(weekly)}")

swing_lows = [j for j in range(we.PIVOT_L, len(daily) - we.PIVOT_R) if we.is_swing_low(daily, j)]
print("swing_lows:", len(swing_lows))

n_w1 = n_sweep = n_d2 = n_ob = n_touch = n_h3 = n_tp = 0
examples = {"w1": None, "sweep": None, "d2": None, "ob": None, "touch": None, "h3": None, "tp": None}
for i in range(20, len(daily) - 3):
    b = daily[i]
    wok, wwhy = we.weekly_permission(weekly, b["t"])
    if wok:
        n_w1 += 1
        if examples["w1"] is None: examples["w1"] = (i, b["t"], wwhy)
    swept = None
    for j in reversed(swing_lows):
        if j + we.PIVOT_R >= i:
            continue
        ssl = daily[j]["l"]
        if b["l"] <= ssl * (1 - we.SWEEP_PCT) and b["c"] > ssl:
            swept = j
            break
    if swept is None:
        continue
    n_sweep += 1
    if examples["sweep"] is None: examples["sweep"] = (i, b["t"], swept)
    rsp = i + 1
    swing_high_vis = max(daily[k]["h"] for k in range(swept, i + 1))
    if not (daily[rsp]["c"] > swing_high_vis):
        continue
    n_d2 += 1
    if examples["d2"] is None: examples["d2"] = (i, b["t"])
    ob_idx = None
    for k in range(rsp + 1, min(len(daily), rsp + 5)):
        if daily[k]["c"] < daily[k]["o"]:
            ob_idx = k
            break
    if ob_idx is None:
        continue
    n_ob += 1
    if examples["ob"] is None: examples["ob"] = (i, b["t"], ob_idx)
    ob = daily[ob_idx]
    zl = min(ob["o"], ob["c"], ob["l"])
    zh = min(max(ob["o"], ob["c"]), zl + (ob["h"] - zl) * 0.5)
    touched = False
    t_idx = None
    entry = None
    for k in range(ob_idx + 1, min(len(daily) - 1, ob_idx + 8)):
        bb = daily[k]
        if bb["l"] <= zl and bb["c"] <= zh:
            if touched:
                break
            touched, t_idx = True, k
            continue
        if bb["c"] < zl:
            if touched:
                break
            touched, t_idx = True, k
            continue
        if bb["l"] <= zh and bb["h"] >= zl:
            touched = True
            t_idx = t_idx if t_idx is not None else k
        if touched and k != t_idx and bb["c"] > zh:
            h3 = max(daily[m]["h"] for m in range(max(0, t_idx - 3), k + 1))
            if bb["c"] > h3:
                entry_idx = k + 1
                if entry_idx < len(daily):
                    entry = (entry_idx, k, t_idx)
            break
    if entry is None:
        continue
    n_touch += 1
    if examples["touch"] is None: examples["touch"] = (i, b["t"], entry)
    entry_idx, reclaim_idx, touch_idx = entry
    entry_price = we.f(daily[entry_idx]["o"])
    tgt = None
    for j in range(entry_idx - we.PIVOT_R - 1, we.PIVOT_L - 1, -1):
        if we.is_swing_high(daily, j) and daily[j]["h"] > max(zh, entry_price):
            tgt = (j, daily[j]["h"])
            break
    if tgt is None:
        continue
    n_tp += 1
    if examples["tp"] is None: examples["tp"] = (i, b["t"], tgt, entry_price)

print(f"W1={n_w1} sweep={n_sweep} D2={n_d2} OB={n_ob} touch/H3={n_touch} TP={n_tp}")
for k, v in examples.items():
    print(f"  {k}: {v}")
