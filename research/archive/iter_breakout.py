# -*- coding: utf-8 -*-
"""第三方向：横盘蓄势突破（accumulation breakout）
ACCUM 阶段（底部吸筹）→ 突破 swing high（BOS 启动）→ 回踩确认 → 入场
大资金行为：吸筹完成 → 突破拉升（区别于反转的扫损、延续的回撤）"""
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


def is_swing_high(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["h"] > max(bs[k]["h"] for k in range(j - PIVOT, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + PIVOT + 1))


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


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


def build_breakout(sym, daily):
    """ACCUM (bottom accumulation) -> close breaks recent swing high (BOS start)
    -> pullback to breakout level (support) -> reclaim -> entry next open."""
    seeds = []
    swing_highs = [j for j in range(PIVOT, len(daily) - PIVOT) if is_swing_high(daily, j)]
    for i in range(80, len(daily) - 3):
        st = stage_detailed(daily, i)
        if st != "ACCUM":
            continue
        # BOS: close breaks a recent swing high that was a prior barrier
        ref = None
        for j in reversed(swing_highs):
            if j + PIVOT >= i:
                continue
            sh = daily[j]["h"]
            # prior closes below sh (range), then close breaks
            if daily[i - 1]["c"] < sh and daily[i]["c"] > sh:
                ref = j
                break
        if ref is None:
            continue
        brk_level = daily[ref]["h"]
        # pullback: within 5 days, low touches breakout level (support), close holds above
        touched = False
        touch_i = None
        for k in range(i + 1, min(len(daily), i + 6)):
            if daily[k]["l"] <= brk_level:
                touched, touch_i = True, k
            if touched and daily[k]["c"] > brk_level and k != touch_i:
                entry_idx = k + 1
                if entry_idx < len(daily):
                    ep = daily[entry_idx]["o"]
                    # SL: below breakout level or recent swing low
                    sl_tmp = None
                    for j in range(k, PIVOT - 1, -1):
                        if is_swing_low(daily, j):
                            sl_tmp = daily[j]["l"]
                            break
                    sl = min(brk_level, sl_tmp or brk_level) * 0.99 if sl_tmp else brk_level * 0.99
                    if sl < ep:
                        seeds.append({"symbol": sym, "entry_idx": entry_idx,
                                      "entry_date": daily[entry_idx]["t"], "ep": ep, "sl": sl,
                                      "brk": brk_level})
                break
    return seeds


def replay(seed, daily):
    entry_idx = int(seed["entry_idx"])
    if entry_idx >= len(daily) - 1:
        return None
    ep = seed["ep"]
    sl = seed["sl"]
    if sl >= ep:
        return None
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
    return {"symbol": seed["symbol"], "entry_date": seed["entry_date"],
            "net_pnl_pct": round(pnl - FEE, 4), "t1_violation": "False"}


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
    for sd in build_breakout(sym, daily):
        tr = replay(sd, daily)
        if tr:
            trades.append(tr)
    if n % 1500 == 0:
        print(f"  {n} files, trades {len(trades)}", flush=True)
print(f"横盘突破 trades: {len(trades)}")


def report(label, rs):
    if len(rs) < 200:
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


print("\n=== 第三方向：横盘蓄势突破 ===")
report("ACCUM突破+回踩（TP2）", trades)
