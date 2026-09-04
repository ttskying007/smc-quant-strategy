# -*- coding: utf-8 -*-
"""延续腿时间结构：MARKUP 支撑回踩信号的跨度（回踩→信号→入场）
+ 支撑形成时间（swing low 距今多久）→ 验证延续信号时效性"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3


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


sigs = []
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
        if not (daily[i]["l"] <= daily[sl_idx]["l"] * 1.01 and daily[i - 1]["c"] > daily[sl_idx]["l"]):
            continue
        if daily[i]["c"] <= daily[sl_idx]["l"]:
            continue
        entry_idx = i + 1
        if entry_idx + 11 >= len(daily):
            continue
        ep = daily[entry_idx]["o"]
        if daily[sl_idx]["l"] >= ep:
            continue
        sigs.append({"entry_date": daily[entry_idx]["t"],
                     "net_pnl_pct": round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - 0.20, 4),
                     "support_age": i - sl_idx})  # 支撑（swing low）距今天数
print("延续信号:", len(sigs))

ages = sorted(s["support_age"] for s in sigs)
n = len(ages)
print("\n=== 支撑形成时间（swing low 距今）===")
print(f"  P25: {ages[n//4]} | P50: {ages[n//2]} | P75: {ages[3*n//4]} | 平均: {sum(ages)/n:.1f}")
print(f"  0-5天: {sum(1 for x in ages if x<=5)/n:.0%} | 6-20天: {sum(1 for x in ages if 6<=x<=20)/n:.0%} | >20天: {sum(1 for x in ages if x>20)/n:.0%}")

# return by support age
print("\n=== 支撑年龄分组收益 ===")
for lo, hi, label in ((0, 5, "新支撑(0-5天)"), (6, 20, "中(6-20天)"), (21, 100, "旧支撑(>20天)")):
    rs = [s for s in sigs if lo <= s["support_age"] <= hi]
    if len(rs) < 50:
        print(f"  {label}: n={len(rs)} (过小)")
        continue
    pnls = [s["net_pnl_pct"] for s in rs]
    wins = [x for x in pnls if x > 0]
    pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
    print(f"  {label}: n={len(rs)} avg={sum(pnls)/len(pnls):+.2f}% 胜率={100*len(wins)/len(rs):.0f}% PF={pf:.2f}")
