# -*- coding: utf-8 -*-
"""SMC 反转腿入场模式：POI 回撤入场（当前）vs CHOCH 突破直接入场
事件腿突破优于回撤（+6.03 vs +4.94）；SMC 腿是否也如此？"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
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
        o, h, l, c, v = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c")), we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


def is_swing_high(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["h"] > max(bs[k]["h"] for k in range(j - PIVOT, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + PIVOT + 1))


def stage_detailed(bs, i):
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


def vwap5_ok(bs, i):
    if i < 20:
        return False
    pv = sum(bs[k]["c"] * bs[k]["v"] for k in range(i - 19, i + 1))
    vol = sum(bs[k]["v"] for k in range(i - 19, i + 1))
    if vol <= 0:
        return False
    vw = pv / vol
    return (bs[i]["c"] - vw) / vw >= 0.05


# Collect: POI retrace entries (current v20c SMC reversal leg) + breakout entries
poi_trades = []  # from wdh build_seeds (retrace to POI + reclaim)
brk_trades = []  # CHOCH breakout: after SSL sweep, close breaks swing high -> entry next open
n = 0
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    n += 1
    daily = bars(os.path.join(KT, p))
    if len(daily) < 400:
        continue
    sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
    # POI retrace (current): build_seeds with R20 + stage + FVG + VWAP5% filters
    for sd in we.build_seeds(sym, daily):
        r20 = sd.get("r20")
        if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
            continue
        entry_idx = int(sd["entry_idx"])
        if entry_idx < 61:
            continue
        st = stage_detailed(daily, entry_idx)
        if st not in ("UPTREND", "MARKUP"):
            continue
        if not any(daily[k]["h"] < daily[k - 2]["l"] for k in range(max(3, entry_idx - 12), entry_idx)):
            continue
        if not vwap5_ok(daily, entry_idx):
            continue
        tr = we.replay_tp2(sd, daily)
        if tr:
            poi_trades.append(tr)
    # breakout: SSL sweep -> CHOCH close break -> entry next open (no POI retrace)
    swing_highs = [j for j in range(PIVOT, len(daily) - PIVOT) if is_swing_high(daily, j)]
    for i in range(PIVOT + 5, len(daily) - 3):
        ref = None
        for j in reversed(swing_highs):
            if j + PIVOT >= i:
                continue
            sh = daily[j]["h"]
            if daily[i - 1]["c"] < sh and daily[i]["c"] > sh:
                ref = j
                break
        if ref is None:
            continue
        entry_idx = i + 1
        if entry_idx >= len(daily) or entry_idx < 61:
            continue
        r20 = daily[entry_idx - 1]["c"] / daily[entry_idx - 21]["c"] - 1
        if not (0 <= r20 < 0.15):
            continue
        st = stage_detailed(daily, entry_idx)
        if st not in ("UPTREND", "MARKUP"):
            continue
        if not vwap5_ok(daily, entry_idx):
            continue
        ep = daily[entry_idx]["o"]
        # SL: recent swing low
        sl = None
        for j in range(i, PIVOT - 1, -1):
            if j < PIVOT:
                break
        lo_min = min(daily[k]["l"] for k in range(max(0, i - 15), i))
        sl = lo_min * 0.99
        if sl >= ep:
            continue
        # TP2 replay
        risk = ep - sl
        tp1 = ep + risk
        tp2 = ep + 2 * risk
        pnl = 0.0
        remaining = 1.0
        be = False
        for k in range(entry_idx + 1, min(len(daily), entry_idx + MAX_HOLD + 1)):
            bb = daily[k]
            hi, lo, cl = bb["h"], bb["l"], bb["c"]
            stop = (ep if be else sl)
            if lo <= stop:
                pnl += remaining * (stop / ep - 1) * 100
                remaining = 0
                break
            if not be and hi >= tp1:
                pnl += 0.40 * (tp1 / ep - 1) * 100
                remaining = 0.60
                be = True
                continue
            if be and hi >= tp2:
                pnl += remaining * (tp2 / ep - 1) * 100
                remaining = 0
                break
        if remaining > 0:
            last = daily[min(len(daily), entry_idx + MAX_HOLD) - 1]["c"]
            pnl += remaining * (last / ep - 1) * 100
        brk_trades.append({"symbol": sym, "entry_date": daily[entry_idx]["t"],
                           "net_pnl_pct": round(pnl - FEE, 4), "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, poi {len(poi_trades)}, brk {len(brk_trades)}", flush=True)
print(f"POI回撤: {len(poi_trades)} | 突破: {len(brk_trades)}")


def report(label, rs):
    if len(rs) < 50:
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


print("\n=== SMC 反转腿入场模式 ===")
report("POI 回撤（当前）", poi_trades)
report("CHOCH 突破直接买", brk_trades)
