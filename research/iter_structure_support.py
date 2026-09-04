# -*- coding: utf-8 -*-
"""深化结构支撑回撤（趋势延续唯一有效变体 +1.01%/PF 1.64）
加过滤：R20 / VWAP / 阶段细分（UPTREND vs MARKUP）/ 回撤深度 → 找最优子集"""
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


rows = []
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
        if st not in ("UPTREND", "MARKUP"):
            continue
        # swing-low support retrace
        sl_tmp = None
        sl_idx = None
        for j in range(i, PIVOT - 1, -1):
            if is_swing_low(daily, j):
                sl_tmp = daily[j]["l"]
                sl_idx = j
                break
        if sl_tmp is None:
            continue
        if not (daily[i]["l"] <= sl_tmp * 1.01 and daily[i - 1]["c"] > sl_tmp):
            continue
        if daily[i]["c"] <= sl_tmp:
            continue  # close reclaim above support
        entry_idx = i + 1
        if entry_idx >= len(daily):
            continue
        ep = daily[entry_idx]["o"]
        if sl_tmp >= ep:
            continue
        sl = sl_tmp * 0.99
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
        # features for sub-analysis
        r20 = daily[entry_idx - 1]["c"] / daily[entry_idx - 21]["c"] - 1 if entry_idx >= 21 else None
        rows.append({"symbol": sym, "entry_date": daily[entry_idx]["t"], "stage": st, "r20": r20,
                     "net_pnl_pct": round(pnl - FEE, 4), "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(rows)}", flush=True)
print(f"结构支撑回撤 rows: {len(rows)}")


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


print("\n=== 结构支撑回撤深化 ===")
valid = [r for r in rows if r["r20"] is not None]
report("基线（全部）", valid)
report("R20<0.15（温和）", [r for r in valid if 0 <= r["r20"] < 0.15])
report("R20<0.10（更早）", [r for r in valid if 0 <= r["r20"] < 0.10])
report("UPTREND 仅", [r for r in valid if r["stage"] == "UPTREND"])
report("MARKUP 仅", [r for r in valid if r["stage"] == "MARKUP"])
report("UPTREND + R20<0.15", [r for r in valid if r["stage"] == "UPTREND" and 0 <= r["r20"] < 0.15])
