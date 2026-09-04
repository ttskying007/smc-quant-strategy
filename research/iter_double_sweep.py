# -*- coding: utf-8 -*-
"""Dimension C2: double-sweep signal (both SSL and BSL raided before POI reclaim).
Large-money two-sided liquidity harvest -> strongest reversal setup.
SSL sweep down + BSL sweep up within N bars, then demand POI reclaim, entry next open."""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3
SWEEP_PCT = 0.003
MAX_HOLD = 40
FEE = 0.20
SL_BUFFER = 0.99


def f(x, d=0.0):
    try:
        return float(x) if x not in (None, "") else d
    except Exception:
        return d


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def is_swing_low(ks, j):
    if j < PIVOT or j + PIVOT >= len(ks):
        return False
    return ks[j]["l"] < min(ks[k]["l"] for k in range(j - PIVOT, j)) and ks[j]["l"] <= min(ks[k]["l"] for k in range(j + 1, j + PIVOT + 1))


def is_swing_high(ks, j):
    if j < PIVOT or j + PIVOT >= len(ks):
        return False
    return ks[j]["h"] > max(ks[k]["h"] for k in range(j - PIVOT, j)) and ks[j]["h"] >= max(ks[k]["h"] for k in range(j + 1, j + PIVOT + 1))


def build_double_sweep(sym, daily):
    seeds = []
    lows = [j for j in range(PIVOT, len(daily) - PIVOT) if is_swing_low(daily, j)]
    highs = [j for j in range(PIVOT, len(daily) - PIVOT) if is_swing_high(daily, j)]
    for i in range(PIVOT + 2, len(daily) - 3):
        b = daily[i]
        # SSL sweep on bar i (down raid)
        ssl_sweep = None
        for j in reversed(lows):
            if j + PIVOT >= i:
                continue
            ssl = daily[j]["l"]
            if b["l"] <= ssl * (1 - SWEEP_PCT) and b["c"] > ssl:
                ssl_sweep = j
                break
        if ssl_sweep is None:
            continue
        # BSL sweep within prior 6 bars (up raid before the down raid = two-sided harvest)
        bsl_sweep = None
        for k in range(max(PIVOT + 1, i - 6), i):
            for j in reversed(highs):
                if j + PIVOT >= k:
                    continue
                bsl = daily[j]["h"]
                if daily[k]["h"] >= bsl * (1 + SWEEP_PCT) and daily[k]["c"] < bsl:
                    bsl_sweep = j
                    break
            if bsl_sweep is not None:
                break
        if bsl_sweep is None:
            continue
        # response + demand OB + touch/reclaim + entry
        rsp = i + 1
        if rsp >= len(daily) or not (daily[rsp]["c"] > b["h"]):
            continue
        ob_idx = None
        for k in range(rsp + 1, min(len(daily), rsp + 5)):
            if daily[k]["c"] < daily[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            continue
        ob = daily[ob_idx]
        zl = min(ob["o"], ob["c"], ob["l"])
        zh = min(max(ob["o"], ob["c"]), zl + (ob["h"] - zl) * 0.5)
        touched = False
        t_idx = None
        entry = None
        for k in range(ob_idx + 1, min(len(daily) - 1, ob_idx + 12)):
            bb = daily[k]
            if bb["l"] <= zl and bb["c"] <= zh:
                if touched:
                    break
                touched, t_idx = True, k
                continue
            if bb["l"] <= zh and bb["h"] >= zl:
                touched = True
                t_idx = t_idx if t_idx is not None else k
            if touched and k != t_idx and bb["c"] > zh:
                entry_idx = k + 1
                if entry_idx < len(daily):
                    entry = (entry_idx, k, t_idx)
                break
        if entry is None:
            continue
        entry_idx, reclaim_idx, touch_idx = entry
        ep = f(daily[entry_idx]["o"])
        # TP: recent swing high above entry (pre-entry)
        tgt = None
        for j in range(entry_idx - PIVOT - 1, PIVOT - 1, -1):
            if is_swing_high(daily, j) and daily[j]["h"] > max(zh, ep):
                tgt = daily[j]["h"]
                break
        if tgt is None:
            continue
        seeds.append({"symbol": sym, "entry_idx": entry_idx, "entry_date": daily[entry_idx]["t"],
                      "event_date": daily[i]["t"], "zone_low": zl, "zone_high": zh,
                      "entry_price": ep, "target": tgt})
    return seeds


def replay(seed, daily):
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = f(seed["entry_price"])
    sl = f(seed["zone_low"]) * SL_BUFFER
    tgt = f(seed["target"])
    risk = ep - sl
    if risk <= 0 or tgt <= ep:
        return None
    exit_price, reason, hold = ep, "TIME_STOP", 0
    for k in range(entry_idx + 1, min(len(daily), entry_idx + MAX_HOLD + 1)):
        bb = daily[k]
        hold += 1
        hi, lo, cl = bb["h"], bb["l"], bb["c"]
        if lo <= sl:
            exit_price, reason = sl, "SL_HIT"
            break
        if hi >= tgt:
            exit_price, reason = tgt, "TP_STRUCTURAL"
            break
        exit_price = cl
    if reason == "TIME_STOP":
        exit_price = daily[min(len(daily), entry_idx + MAX_HOLD) - 1]["c"]
    return {"symbol": seed["symbol"], "entry_date": seed["entry_date"],
            "net_pnl_pct": round((exit_price / ep - 1) * 100 - FEE, 4), "reason": reason,
            "hold_bars": hold, "t1_violation": "False"}


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
    for sd in build_double_sweep(sym, daily):
        tr = replay(sd, daily)
        if tr:
            trades.append(tr)
    if n % 1500 == 0:
        print(f"  {n} files, trades {len(trades)}", flush=True)
print(f"double-sweep trades: {len(trades)}")
for t in trades:
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
gate = check_economic_gate(trades)
o = gate["overall"]
print(f"\n=== 双扫信号（SSL+BSL 双向流动性收割）===")
print(f"总体: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']} gate={gate['gate_pass']}")
for y in ("2024", "2025", "2026"):
    ys = [t for t in trades if str(t["entry_date"]).startswith(y)]
    if ys:
        wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
        print(f"  {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")
