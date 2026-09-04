# -*- coding: utf-8 -*-
"""CHOCH + POI retrace signal: structure shift (close breaks swing high after
down-move) then retrace into a demand OB/FVG, reclaim, entry next open.
Adds SMC supply beyond SSL sweep (diversify signal types per user)."""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3
MAX_HOLD = 40
FEE = 0.20
SL_BUF = 0.99


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
        o, h, l, c, v = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c")), f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
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


def build_choch(sym, daily):
    """CHOCH: after a down-swing, close breaks the most recent swing high (structure shift),
    then pullback into demand OB (bullish bar), reclaim, entry next open."""
    seeds = []
    swing_highs = [j for j in range(PIVOT, len(daily) - PIVOT) if is_swing_high(daily, j)]
    for i in range(PIVOT + 5, len(daily) - 3):
        # CHOCH: close above most recent swing high, after price was below it
        ref = None
        for j in reversed(swing_highs):
            if j + PIVOT >= i:
                continue
            sh = daily[j]["h"]
            # prior closes below sh (down context), then close breaks
            if daily[i - 1]["c"] < sh and daily[i]["c"] > sh:
                ref = j
                break
        if ref is None:
            continue
        # demand OB: first bullish bar after CHOCH
        ob_idx = None
        for k in range(i + 1, min(len(daily), i + 5)):
            if daily[k]["c"] > daily[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            continue
        ob = daily[ob_idx]
        zl = min(ob["o"], ob["c"], ob["l"])
        zh = max(ob["o"], ob["c"])
        # retrace into zone then reclaim (close above zh)
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
        # r20 + stage filters
        if entry_idx < 21:
            continue
        r20 = daily[entry_idx - 1]["c"] / daily[entry_idx - 21]["c"] - 1
        if not (0 <= r20 < 0.15):
            continue
        if entry_idx < 61:
            continue
        w60 = daily[entry_idx - 60:entry_idx]
        w20 = daily[entry_idx - 20:entry_idx]
        ret60 = w60[-1]["c"] / w60[0]["c"] - 1
        v20 = sum(x["v"] for x in w20) / len(w20)
        v60 = sum(x["v"] for x in w60) / len(w60)
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
        # TP: swing high above entry
        tgt = None
        for j in range(entry_idx - PIVOT - 1, PIVOT - 1, -1):
            if is_swing_high(daily, j) and daily[j]["h"] > max(zh, ep):
                tgt = daily[j]["h"]
                break
        if tgt is None:
            continue
        seeds.append({"symbol": sym, "entry_idx": entry_idx, "entry_date": daily[entry_idx]["t"],
                      "zone_low": zl, "zone_high": zh, "entry_price": ep, "target": tgt})
    return seeds


def replay(seed, daily):
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = f(seed["entry_price"])
    sl = f(seed["zone_low"]) * SL_BUF
    tgt = f(seed["target"])
    risk = ep - sl
    if risk <= 0 or tgt <= ep:
        return None
    # TP2-style: 1R partial + runner to target
    tp1 = ep + risk
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
            exit_price = tp1
            continue
        if be and hi >= tgt:
            pnl += remaining * (tgt / ep - 1) * 100
            reason = "TP_STRUCTURAL"
            remaining = 0
            break
        exit_price = cl
    if remaining > 0:
        last = daily[min(len(daily), entry_idx + MAX_HOLD) - 1]["c"]
        pnl += remaining * (last / ep - 1) * 100
        reason = "TIME_STOP"
    return {"symbol": seed["symbol"], "entry_date": seed["entry_date"],
            "net_pnl_pct": round(pnl - FEE, 4), "reason": reason,
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
    for sd in build_choch(sym, daily):
        tr = replay(sd, daily)
        if tr:
            trades.append(tr)
    if n % 1500 == 0:
        print(f"  {n} files, trades {len(trades)}", flush=True)
print(f"CHOCH trades: {len(trades)}")
for t in trades:
    t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
gate = check_economic_gate(trades)
o = gate["overall"]
print(f"\n=== CHOCH + POI 回踩（独立信号）===")
print(f"总体: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']} gate={gate['gate_pass']}")
for y in ("2024", "2025", "2026"):
    ys = [t for t in trades if str(t["entry_date"]).startswith(y)]
    if ys:
        wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
        print(f"  {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")
print("\n对比 SSL sweep 链: n=377 avg=+2.57%（R20+阶段）")
