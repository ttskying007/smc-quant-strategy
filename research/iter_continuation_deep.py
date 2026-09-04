# -*- coding: utf-8 -*-
"""延续腿独立策略深化：MARKUP 结构支撑回撤（+1.62%/PF 2.15）
加过滤找最优子集：VWAP / 波动率 / 回撤深度 / 事件叠加"""
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
        # features
        r20 = daily[entry_idx - 1]["c"] / daily[entry_idx - 21]["c"] - 1 if entry_idx >= 21 else None
        pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
        vwap_dev = (daily[entry_idx]["c"] - pv / vol) / (pv / vol) if vol and pv else None
        w20 = daily[entry_idx - 20:entry_idx]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / len(w20) if len(w20) == 20 else None
        depth = (daily[i]["l"] / sl_tmp - 1) if sl_tmp else None  # negative=below support
        rows.append({"symbol": sym, "entry_date": daily[entry_idx]["t"], "r20": r20,
                     "vwap_dev": vwap_dev, "vol20": vol20, "depth": depth,
                     "net_pnl_pct": round(pnl - FEE, 4), "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(rows)}", flush=True)
print(f"MARKUP 结构支撑 rows: {len(rows)}")


def report(label, rs):
    if len(rs) < 300:
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


print("\n=== 延续腿深化（MARKUP 结构支撑）===")
valid = [r for r in rows if r["r20"] is not None and r["vwap_dev"] is not None and r["vol20"] is not None]
report("基线（全部）", valid)
report("+VWAP dev>=3%", [r for r in valid if r["vwap_dev"] >= 0.03])
report("+VWAP dev>=5%", [r for r in valid if r["vwap_dev"] >= 0.05])
v = sorted(r["vol20"] for r in valid)
vmed = v[len(v) // 2]
report("+高波动(vol>中位)", [r for r in valid if r["vol20"] > vmed])
report("+VWAP5% + 高波动", [r for r in valid if r["vwap_dev"] >= 0.05 and r["vol20"] > vmed])
report("+回撤深(depth<-0.02)", [r for r in valid if r["depth"] is not None and r["depth"] < -0.02])
