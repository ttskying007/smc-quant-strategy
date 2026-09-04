# -*- coding: utf-8 -*-
"""SMC 趋势延续（动量中继）：UPTREND/MARKUP 中回撤到 MA20/结构支撑后收回买入
vs 当前 SMC 反转（SSL sweep 触底）。
回答：SMC 趋势延续方向有没有 alpha？"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3
MAX_HOLD = 40
FEE = 0.20


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


def ma20(bs, i):
    if i < 20:
        return None
    return sum(b["c"] for b in bs[i - 19:i + 1]) / 20


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def build_continuation(sym, daily):
    """UPTREND/MARKUP + retrace to MA20 (low <= MA20) + close reclaim above MA20 -> next open entry."""
    seeds = []
    for i in range(80, len(daily) - 2):
        w60 = daily[i - 60:i]
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(x["v"] for x in daily[i - 20:i]) / 20
        v60 = sum(x["v"] for x in daily[i - 60:i]) / 60
        vt = v20 / v60 if v60 else 1
        if ret60 < -0.15 and vt < 0.9:
            st = "ACCUM"
        elif ret60 > 0.30 and vt > 1.3:
            st = "DISTRIB"
        elif ret60 > 0.20 and vt > 1.1:
            st = "MARKUP"
        elif ret60 > 0:
            st = "UPTREND"
        else:
            st = "DOWNTREND"
        if st not in ("UPTREND", "MARKUP"):
            continue
        m = ma20(daily, i)
        if m is None:
            continue
        # retrace: today low <= MA20, previous close > MA20 (pullback into MA)
        if not (daily[i]["l"] <= m and daily[i - 1]["c"] > m):
            continue
        # reclaim: close back above MA20
        if daily[i]["c"] <= m:
            continue
        entry_idx = i + 1
        if entry_idx >= len(daily):
            continue
        ep = daily[entry_idx]["o"]
        # structure SL: recent swing low (support)
        sl = None
        for j in range(i, PIVOT - 1, -1):
            if is_swing_low(daily, j):
                sl = daily[j]["l"]
                break
        if sl is None or sl >= ep:
            continue
        seeds.append({"symbol": sym, "entry_idx": entry_idx, "entry_date": daily[entry_idx]["t"],
                      "entry_price": ep, "sl": sl * 0.99, "ma": m})
    return seeds


def replay(seed, daily):
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = seed["entry_price"]
    sl = seed["sl"]
    if sl >= ep:
        return None
    # TP2-style: 1R partial + runner to 2R
    risk = ep - sl
    tp1 = ep + risk
    tp2 = ep + 2 * risk
    exit_price, reason, hold = ep, "TIME_STOP", 0
    pnl = 0.0
    remaining = 1.0
    be = False
    for k in range(entry_idx + 1, min(len(daily), entry_idx + MAX_HOLD + 1)):
        bb = daily[k]
        hold += 1
        hi, lo, cl = bb["h"], bb["l"], bb["c"]
        stop = (ep if be else sl)
        if lo <= stop:
            pnl += remaining * (stop / ep - 1) * 100
            reason = "BE" if be else "SL_HIT"
            remaining = 0
            break
        if not be and hi >= tp1:
            pnl += 0.40 * (tp1 / ep - 1) * 100
            remaining = 0.60
            be = True
            continue
        if be and hi >= tp2:
            pnl += remaining * (tp2 / ep - 1) * 100
            reason = "TP2"
            remaining = 0
            break
        exit_price = cl
    if remaining > 0:
        last = daily[min(len(daily), entry_idx + MAX_HOLD) - 1]["c"]
        pnl += remaining * (last / ep - 1) * 100
        reason = "TIME_STOP"
    return {"symbol": seed["symbol"], "entry_date": seed["entry_date"],
            "net_pnl_pct": round(pnl - FEE, 4), "reason": reason, "t1_violation": "False"}


trades = []
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    for sd in build_continuation(sym, daily):
        tr = replay(sd, daily)
        if tr:
            trades.append(tr)
    if n % 1500 == 0:
        print(f"  {n} files, trades {len(trades)}", flush=True)
print(f"SMC 趋势延续 trades: {len(trades)}")


def report(label, rs):
    if len(rs) < 100:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== SMC 趋势延续（UPTREND回撤MA20收回）vs SMC 反转（SSL sweep）===")
report("SMC 趋势延续（动量中继）", trades)
print("对比：SMC 反转（SSL sweep+R20+阶段+FVG+VWAP5%）= +4.32%（v18 SMC 腿）")
