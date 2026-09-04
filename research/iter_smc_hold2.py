# -*- coding: utf-8 -*-
"""SMC 腿 MAX_HOLD 优化验证（新）：40（当前）vs 15 vs 10 天时间止损
用 MSS 反转信号回放对比（MSS 3-5 日胜率 86% → 缩短持有是否提升）"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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


def detect_mss_bull(bs, i):
    if i < 5 or i + 3 >= len(bs):
        return None
    prev_lows = [bs[j]["l"] for j in range(i - 5, i)]
    if not prev_lows or bs[i]["l"] >= min(prev_lows):
        return None
    if bs[i + 1]["c"] <= bs[i - 1]["h"] and bs[i + 2]["c"] <= bs[i - 1]["h"]:
        return None
    if (max(bs[i + 1]["h"], bs[i + 2]["h"], bs[i + 3]["h"]) - bs[i]["l"]) / bs[i]["l"] < 0.015:
        return None
    return i


files = sorted([f for f in os.listdir(KT) if f.endswith("_daily_800.json")])[:120]
mss_list = []
for f in files:
    bars = load_bars(os.path.join(KT, f))
    if len(bars) < 400:
        continue
    for i in range(20, len(bars) - 42):
        if detect_mss_bull(bars, i) is not None:
            ep = bars[i + 1]["o"]
            sl = bars[i]["l"] * 0.99
            if sl >= ep or ep <= 0:
                continue
            r = ep - sl
            mss_list.append({"bs": bars, "entry_idx": i + 1, "ep": ep, "sl": sl,
                             "tp1": ep + r, "tp2": ep + 2 * r, "entry_date": bars[i + 1]["t"]})
print("MSS 交易样本:", len(mss_list))


def simulate(max_hold):
    out = []
    for m in mss_list:
        ep = m["ep"]
        remaining = 1.0
        net = 0.0
        be = False
        for k in range(m["entry_idx"] + 1, min(len(m["bs"]), m["entry_idx"] + max_hold + 1)):
            bb = m["bs"][k]
            stop = ep if be else m["sl"]
            if bb["l"] <= stop:
                net += remaining * (stop / ep - 1) * 100
                remaining = 0
                break
            if not be and bb["h"] >= m["tp1"]:
                net += 0.4 * (m["tp1"] / ep - 1) * 100
                remaining = 0.6
                be = True
            elif be and bb["h"] >= m["tp2"]:
                net += remaining * (m["tp2"] / ep - 1) * 100
                remaining = 0
                break
        if remaining > 0:
            last = m["bs"][min(len(m["bs"]), m["entry_idx"] + max_hold) - 1]["c"]
            net += remaining * (last / ep - 1) * 100
        out.append({"entry_date": m["entry_date"], "net_pnl_pct": round(net - 0.20, 4)})
    return out


print("\n=== SMC 腿 MAX_HOLD 优化对比 ===")
for mh in (40, 15, 10, 5):
    rs = simulate(mh)
    pnls = [t["net_pnl_pct"] for t in rs]
    wins = [x for x in pnls if x > 0]
    avg = sum(pnls) / len(pnls)
    pf = sum(wins) / abs(sum(x for x in pnls if x <= 0)) if any(x <= 0 for x in pnls) else 99
    print(f"  MAX_HOLD={mh}: n={len(rs)} avg={avg:+.2f}% 胜率={100*len(wins)/len(rs):.0f}% PF={pf:.2f}")
