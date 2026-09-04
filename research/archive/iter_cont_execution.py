# -*- coding: utf-8 -*-
"""延续腿执行优化：MARKUP+结构支撑+VWAP5%（信号已最优 +3.94%）
出场变体：TP2（当前）vs 固定持有 10/15 日 vs 结构 TP 前高"""
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


def is_swing_low(bs, j):
    if j < PIVOT or j + PIVOT >= len(bs):
        return False
    return bs[j]["l"] < min(bs[k]["l"] for k in range(j - PIVOT, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + PIVOT + 1))


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


def collect_signals():
    """Collect MARKUP+struct+vwap5% signals with entry_idx/entry/sl/tp_swing for replay variants."""
    sigs = []
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
            st = stage_detailed(daily, i)
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
            if entry_idx >= len(daily) or entry_idx < 20:
                continue
            ep = daily[entry_idx]["o"]
            if sl_tmp >= ep:
                continue
            pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            if vol <= 0:
                continue
            vw = pv / vol
            if (daily[entry_idx]["c"] - vw) / vw < 0.05:
                continue
            # structural TP: pre-entry swing high
            tp_swing = None
            for j in range(entry_idx - 1, PIVOT - 1, -1):
                if is_swing_high(daily, j) and daily[j]["h"] > ep:
                    tp_swing = daily[j]["h"]
                    break
            sigs.append({"symbol": sym, "entry_date": daily[entry_idx]["t"], "i": entry_idx,
                         "ep": ep, "sl": sl_tmp * 0.99, "tp_swing": tp_swing, "daily": daily})
        if n % 1500 == 0:
            print(f"  {n} files, sigs {len(sigs)}", flush=True)
    return sigs


def replay_tp2(sig):
    daily = sig["daily"]
    i = sig["i"]
    ep, sl = sig["ep"], sig["sl"]
    if sl >= ep:
        return None
    risk = ep - sl
    tp1 = ep + risk
    tp2 = ep + 2 * risk
    pnl = 0.0
    remaining = 1.0
    be = False
    for k in range(i + 1, min(len(daily), i + MAX_HOLD + 1)):
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
        last = daily[min(len(daily), i + MAX_HOLD) - 1]["c"]
        pnl += remaining * (last / ep - 1) * 100
    return round(pnl - FEE, 4)


def replay_hold(sig, hold):
    daily = sig["daily"]
    i = sig["i"]
    ep = sig["ep"]
    if i + hold >= len(daily):
        return None
    return round((daily[i + hold]["c"] / ep - 1) * 100 - FEE, 4)


def replay_struct(sig):
    """Structural: TP = swing high, SL = support low, MSS trailing."""
    daily = sig["daily"]
    i = sig["i"]
    ep, sl = sig["ep"], sig["sl"]
    tp = sig["tp_swing"]
    if sl is None or tp is None or sl >= ep or tp <= ep:
        return None
    exit_px, reason = ep, "TIME_STOP"
    hold = 0
    for k in range(i + 1, min(len(daily), i + MAX_HOLD + 1)):
        bb = daily[k]
        hold += 1
        if bb["l"] <= sl:
            exit_px, reason = sl, "SL_HIT"
            break
        if bb["h"] >= tp:
            exit_px, reason = tp, "TP_STRUCT"
            break
        exit_px = bb["c"]
    if reason == "TIME_STOP":
        exit_px = daily[min(len(daily), i + MAX_HOLD) - 1]["c"]
    return round((exit_px / ep - 1) * 100 - FEE, 4)


sigs = collect_signals()
print("signals:", len(sigs))


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t["t1_violation"] = "False"
        t["year"] = str(t["entry_date"])[:4]
    gate = check_economic_gate(rs)
    o = gate["overall"]
    line = f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']}"
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if t["year"] == y]
        if ys:
            line += f" | {y}:{sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%"
    print(line)


print("\n=== 延续腿执行优化（信号固定：MARKUP+结构+VWAP5%）===")
t_tp2 = [{"entry_date": s["entry_date"], "net_pnl_pct": replay_tp2(s)} for s in sigs]
t_tp2 = [t for t in t_tp2 if t["net_pnl_pct"] is not None]
report("TP2（1R+2R runner）", t_tp2)
for h in (10, 15, 20):
    t_h = [{"entry_date": s["entry_date"], "net_pnl_pct": replay_hold(s, h)} for s in sigs]
    t_h = [t for t in t_h if t["net_pnl_pct"] is not None]
    report(f"固定持有 {h} 日", t_h)
t_st = [{"entry_date": s["entry_date"], "net_pnl_pct": replay_struct(s)} for s in sigs]
t_st = [t for t in t_st if t["net_pnl_pct"] is not None]
report("结构TP（前高）", t_st)
