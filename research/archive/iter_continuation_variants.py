# -*- coding: utf-8 -*-
"""趋势延续变体探索（用户要求：两个方向都研究）
Base SMC continuation (UPTREND retrace MA20) was -0.16% (no edge).
Test variants to find continuation alpha conditions:
- 强趋势: ADX>=25 / ret60>0.5
- 浅回撤: MA10 reclaim (stronger pullback)
- 缩量回撤: retrace day volume < prev avg (healthy pullback)
- 结构支撑: retrace to swing low instead of MA20
- 深回撤: retrace to MA50 (bigger pullback = better entry?)
"""
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


def ma(bs, i, n):
    if i < n:
        return None
    return sum(b["c"] for b in bs[i - n + 1:i + 1]) / n


def adx14(bs, i):
    if i < 30:
        return None
    plus_dm = minus_dm = tr_sum = 0.0
    for k in range(i - 14, i):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
        plus_dm += up if (up > dn and up > 0) else 0
        minus_dm += dn if (dn > up and dn > 0) else 0
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_sum += tr
    if tr_sum <= 0:
        return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0:
        return None
    return 100 * abs(pdi - mdi) / (pdi + mdi)


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def stage(bs, i):
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
    if ret60 > 0:
        return "UPTREND"
    return "DOWNTREND"


def scan(variant):
    """variant: which MA/condition to use."""
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
        for i in range(80, len(daily) - 2):
            st = stage(daily, i)
            if st not in ("UPTREND", "MARKUP"):
                continue
            if variant.get("adx_min"):
                a = adx14(daily, i)
                if a is None or a < variant["adx_min"]:
                    continue
            if variant.get("ret60_min"):
                w60 = daily[i - 60:i]
                if w60[-1]["c"] / w60[0]["c"] - 1 < variant["ret60_min"]:
                    continue
            # retrace condition by variant
            m = ma(daily, i, variant.get("ma_n", 20))
            if m is None:
                continue
            retrace_ok = (daily[i]["l"] <= m and daily[i - 1]["c"] > m)
            if variant.get("ma_strong") and retrace_ok:
                m2 = ma(daily, i, 10)
                retrace_ok = m2 is not None and daily[i]["l"] <= m2 and daily[i - 1]["c"] > m2
            if variant.get("vol_shrink") and retrace_ok:
                avg_v = sum(b["v"] for b in daily[i - 5:i]) / 5
                retrace_ok = avg_v > 0 and daily[i]["v"] < avg_v * 1.2  # no volume spike on retrace
            if variant.get("swing_low") and retrace_ok:
                # retrace to recent swing low support instead of MA
                sl_tmp = None
                for j in range(i, PIVOT - 1, -1):
                    if is_swing_low(daily, j):
                        sl_tmp = daily[j]["l"]
                        break
                retrace_ok = sl_tmp is not None and daily[i]["l"] <= sl_tmp * 1.01 and daily[i - 1]["c"] > sl_tmp
            if not retrace_ok:
                continue
            if daily[i]["c"] <= m:
                continue  # close must reclaim above
            entry_idx = i + 1
            if entry_idx >= len(daily):
                continue
            ep = daily[entry_idx]["o"]
            sl = None
            for j in range(i, PIVOT - 1, -1):
                if is_swing_low(daily, j):
                    sl = daily[j]["l"]
                    break
            if sl is None or sl >= ep:
                continue
            sl = sl * 0.99
            risk = ep - sl
            tp1 = ep + risk
            tp2 = ep + 2 * risk
            pnl = 0.0
            remaining = 1.0
            be = False
            reason = "TIME_STOP"
            for k in range(entry_idx + 1, min(len(daily), entry_idx + MAX_HOLD + 1)):
                bb = daily[k]
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
            if remaining > 0:
                last = daily[min(len(daily), entry_idx + MAX_HOLD) - 1]["c"]
                pnl += remaining * (last / ep - 1) * 100
                reason = "TIME_STOP"
            trades.append({"symbol": sym, "entry_date": daily[entry_idx]["t"],
                           "net_pnl_pct": round(pnl - FEE, 4), "t1_violation": "False"})
        if n % 2000 == 0:
            print(f"  [{variant['name']}] {n} files, {len(trades)} trades", flush=True)
    return trades


def report(label, rs):
    if len(rs) < 100:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


variants = [
    {"name": "基线(MA20收回)", "ma_n": 20},
    {"name": "强趋势ADX>=25", "ma_n": 20, "adx_min": 25},
    {"name": "强动量ret60>=0.4", "ma_n": 20, "ret60_min": 0.4},
    {"name": "浅回撤MA10", "ma_strong": True, "ma_n": 20},
    {"name": "缩量回撤", "ma_n": 20, "vol_shrink": True},
    {"name": "深回撤MA50", "ma_n": 50},
    {"name": "结构支撑回撤", "ma_n": 20, "swing_low": True},
]
print("=== 趋势延续变体探索 ===")
for v in variants:
    trades = scan(v)
    report(v["name"], trades)
    print(flush=True)
