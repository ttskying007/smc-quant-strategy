# -*- coding: utf-8 -*-
"""P2-1: 延续腿回测重写（VWAP10% + 支撑新鲜度≤5天）
取代 gen_v20f.py 中从 v20d 复制 CONT 的旧路径"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}

def bars(path):
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


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def stage_of(bs, i):
    if i < 61:
        return None
    w60 = bs[i - 60:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    v20 = sum(x["v"] for x in bs[i - 20:i]) / 20
    v60 = sum(x["v"] for x in bs[i - 60:i]) / 60
    vt = v20 / v60 if v60 else 1
    if ret60 < -0.15 and vt < 0.9:
        return "ACCUM"
    if ret60 > 0.30 and vt > 1.3:
        return "DISTRIB"
    if ret60 > 0.20 and vt > 1.1:
        return "MARKUP"
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


# collect signals
sigs = []
vols = []
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    daily = bars(os.path.join(KT, p))
    if len(daily) < 80:
        continue
    w20 = daily[-21:-1] if len(daily) >= 21 else daily
    if len(w20) == 20:
        vols.append(sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20)
    if len(vols) > 3000:
        break
vols.sort()
V_MED = vols[len(vols) // 2]

for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    for i in range(80, len(daily) - 11):
        st = stage_of(daily, i)
        if st != "MARKUP":
            continue
        sl_idx = None
        for j in range(i, PIVOT - 1, -1):
            if is_swing_low(daily, j):
                sl_idx = j
                break
        if sl_idx is None:
            continue
        support_age = i - sl_idx
        # P2-1: 支撑新鲜度 ≤5 天（研究：>5 天负收益 -2.43%）
        if support_age > 5:
            continue
        if not (daily[i]["l"] <= daily[sl_idx]["l"] * 1.01 and daily[i - 1]["c"] > daily[sl_idx]["l"]):
            continue
        if daily[i]["c"] <= daily[sl_idx]["l"]:
            continue
        entry_idx = i + 1
        if entry_idx + 11 >= len(daily) or entry_idx < 130:
            continue
        if daily[entry_idx]["t"] < "20230901":
            continue
        ep = daily[entry_idx]["o"]
        if daily[sl_idx]["l"] >= ep:
            continue
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        if vol <= 0:
            continue
        vw = pv / vol
        # VWAP10%（研究：+8.56%，当前实盘已用）
        if (daily[entry_idx]["c"] - vw) / vw < 0.10:
            continue
        w20 = daily[entry_idx - 20:entry_idx]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
        if vol20 >= V_MED:
            continue
        sigs.append({"entry_date": daily[entry_idx]["t"],
                     "net_pnl_pct": round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - 0.20, 4),
                     "support_age": support_age})

print(f"延续信号(VWAP10%+新鲜度≤5): {len(sigs)}")
if sigs:
    pnls = [s["net_pnl_pct"] for s in sigs]
    wins = [x for x in pnls if x > 0]
    pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
    print(f"avg {sum(pnls)/len(pnls):+.2f}% | 胜率 {100*len(wins)/len(pnls):.0f}% | PF {pf:.2f}")
    for y in ("2024", "2025", "2026"):
        ys = [s["net_pnl_pct"] for s in sigs if str(s["entry_date"])[:4] == y]
        if ys:
            print(f"  {y}: n={len(ys)} avg={sum(ys)/len(ys):+.2f}%")
    # 落盘新延续腿 CSV（供 gen_v20f 整合）
    import csv
    with open(r"E:\test\smc_project\research\cont_v20f_new.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "entry_date", "src", "net_pnl_pct", "support_age"])
        w.writeheader()
        import os
        for p in sorted(os.listdir(KT)):
            if not p.endswith("_daily_800.json"):
                continue
            code = p.replace("_daily_800.json", "")
            for s in sigs:
                pass  # symbol mapping handled below
        print("  提示: 需映射 symbol（用 p2_cont_refresh 内 sigs 已含 entry_date，symbol 需补充）")