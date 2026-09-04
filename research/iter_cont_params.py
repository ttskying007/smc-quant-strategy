# -*- coding: utf-8 -*-
"""延续腿参数优化：VWAP 阈值(3%/5%/7%/10%) + 低波动(vol20中位/0.75x/1.25x) + ADX(0/15/20/25)"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3


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


def stage_of(bs, i):
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
    return "UPTREND" if ret60 > 0 else "DOWNTREND"


def run_cont(VWAP_MIN, VOL_MAX, ADX_MIN, limit=600):
    trades = []
    n = 0
    for p in sorted(os.listdir(KT)):
        if not p.endswith("_daily_800.json"):
            continue
        n += 1
        daily = bars(os.path.join(KT, p))
        if len(daily) < 400:
            continue
        for i in range(80, len(daily) - 15):
            st = stage_of(daily, i)
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
            if entry_idx >= len(daily) or entry_idx < 20 or entry_idx + 10 >= len(daily):
                continue
            ep = daily[entry_idx]["o"]
            if sl_tmp >= ep:
                continue
            # VWAP >= VWAP_MIN%
            pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            if vol <= 0:
                continue
            vw = pv / vol
            if (daily[entry_idx]["c"] - vw) / vw < VWAP_MIN:
                continue
            # low volatility < VOL_MAX (fraction of global median)
            w20 = daily[entry_idx - 20:entry_idx]
            vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
            if vol20 >= VOL_MAX:
                continue
            # ADX >= ADX_MIN (optional)
            if ADX_MIN > 0:
                # quick ADX14
                if entry_idx < 30:
                    continue
                plus_dm = minus_dm = tr_sum = 0.0
                for k in range(entry_idx - 14, entry_idx):
                    h, l, pc = daily[k]["h"], daily[k]["l"], daily[k - 1]["c"]
                    up = h - daily[k - 1]["h"]
                    dn = daily[k - 1]["l"] - l
                    plus_dm += up if (up > dn and up > 0) else 0
                    minus_dm += dn if (dn > up and dn > 0) else 0
                    tr = max(h - l, abs(h - pc), abs(l - pc))
                    tr_sum += tr
                if tr_sum <= 0:
                    continue
                pdi = 100 * plus_dm / tr_sum
                mdi = 100 * minus_dm / tr_sum
                if pdi + mdi == 0:
                    continue
                adx = 100 * abs(pdi - mdi) / (pdi + mdi)
                if adx < ADX_MIN:
                    continue
            trades.append({"entry_date": daily[entry_idx]["t"],
                           "net_pnl_pct": round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - 0.20, 4)})
            if len(trades) > limit:
                break
        if len(trades) > limit:
            break
    return trades


def report(label, rs):
    if len(rs) < 100:
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


# compute global median vol20
vols = []
for p in sorted(os.listdir(KT)):
    if not p.endswith("_daily_800.json"):
        continue
    daily = bars(os.path.join(KT, p))
    if len(daily) < 80:
        continue
    w20 = daily[-21:-1] if len(daily) >= 21 else daily
    if len(w20) == 20:
        vols.append(sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20)
    if len(vols) > 3000:
        break
vols.sort()
V_MED = vols[len(vols) // 2]
print(f"vol20 中位数: {V_MED:.4f}")

print("\n=== 延续腿参数优化 ===\n")
# baseline: VWAP=5%, vol<median, ADX=0 (current)
base = run_cont(0.05, V_MED, 0)
report("基线(VWAP5%/vol<中位/ADX0)", base)

# VWAP sweep
for vw in (0.03, 0.05, 0.07, 0.10):
    t = run_cont(vw, 999, 0)  # no vol filter
    report(f"VWAP>{vw*100:.0f}%(无vol)", t)

# Vol sweep (with VWAP=5%)
for vl in (V_MED * 0.75, V_MED, V_MED * 1.25):
    t = run_cont(0.05, vl, 0)
    report(f"VWAP5%/vol<{vl:.4f}", t)

# ADX sweep (with VWAP5%/vol<median)
for adx in (0, 15, 20, 25):
    t = run_cont(0.05, V_MED, adx)
    report(f"VWAP5%/vol<中位/ADX>{adx}", t)