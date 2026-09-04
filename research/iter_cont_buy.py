# -*- coding: utf-8 -*-
"""延续腿买点优化：回踩支撑（支撑价±0.5%）vs T+1 开盘
延续腿信号（MARKUP 结构支撑）的入场位置验证"""
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


def collect_signals():
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
            sl_tmp = None
            for j in range(i, PIVOT - 1, -1):
                if is_swing_low(daily, j):
                    sl_tmp = daily[j]["l"]
                    break
            if sl_tmp is None:
                continue
            if not (daily[i]["l"] <= sl_tmp * 1.01 and daily[i - 1]["c"] > sl_tmp):
                continue
            if daily[i]["c"] <= sl_tmp:
                continue
            entry_idx = i + 1
            if entry_idx + 11 >= len(daily):
                continue
            ep = daily[entry_idx]["o"]
            if sl_tmp >= ep:
                continue
            sigs.append({"daily": daily, "entry_idx": entry_idx, "ep": ep, "support": sl_tmp,
                         "entry_date": daily[entry_idx]["t"]})
    return sigs


sigs = collect_signals()
print("延续信号:", len(sigs))


def sim(entry_mode):
    out = []
    for s in sigs:
        i = s["entry_idx"]
        if i + 10 >= len(s["daily"]):
            continue
        if entry_mode == "open":
            ep = s["ep"]
        elif entry_mode == "retrace":
            # T+1 low <= support → fill at support; else open
            low = s["daily"][i]["l"]
            ep = s["support"] if low <= s["support"] else s["ep"]
        else:  # support always (if T+1 low >= support, still at support — not realistic, skip)
            if s["daily"][i]["l"] > s["support"]:
                continue
            ep = s["support"]
        out.append({"entry_date": s["entry_date"], "net_pnl_pct": round((s["daily"][i + 10]["c"] / ep - 1) * 100 - 0.20, 4)})
    return out


def report(label, rs):
    if len(rs) < 200:
        print(f"{label}: n={len(rs)} (过小)")
        return
    pnls = [t["net_pnl_pct"] for t in rs]
    wins = [x for x in pnls if x > 0]
    pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
    print(f"{label}: n={len(rs)} avg={sum(pnls)/len(pnls):+.2f}% 胜率={100*len(wins)/len(rs):.0f}% PF={pf:.2f}")


print("\n=== 延续腿买点优化 ===")
report("T+1开盘（当前）", sim("open"))
report("回踩支撑成交", sim("retrace"))
report("仅回踩(未回踩跳过)", sim("support"))
