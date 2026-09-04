# -*- coding: utf-8 -*-
"""最终组合验证：所有落地优化整合后 v20c 完整回测
VWAP10% 延续 + 事件(ACCUM/DOWNTREND/ADX20) + SMC 反转 → 对比原 v20c"""
import csv, io, json, os, sqlite3, sys
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


# 1. continuation leg with VWAP10% (optimized)
def cont_leg(vwap_min):
    trades = []
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
    for p in sorted(os.listdir(KT)):
        if not p.endswith("_daily_800.json"):
            continue
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
            pv = sum(daily[k]["c"] * daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            vol = sum(daily[k]["v"] for k in range(entry_idx - 19, entry_idx + 1))
            if vol <= 0:
                continue
            vw = pv / vol
            if (daily[entry_idx]["c"] - vw) / vw < vwap_min:
                continue
            w20 = daily[entry_idx - 20:entry_idx]
            vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
            if vol20 >= V_MED:
                continue
            trades.append({"entry_date": daily[entry_idx]["t"], "src": "CONT",
                           "net_pnl_pct": round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - 0.20, 4)})
    return trades


def report(label, rs):
    if len(rs) < 300:
        print(f"{label}: n={len(rs)} (过小)")
        return
    for t in rs:
        t.setdefault("t1_violation", "False")
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


# load original v20c (VWAP5% continuation) for comparison
orig = []
with open(r"E:\test\smc_project\research\combo_v20c_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        orig.append(r)
# new continuation VWAP10%
cont10 = cont_leg(0.10)
# keep original EVENT + SMC from orig, replace CONT with VWAP10% version
new_all = [t for t in orig if t.get("src") != "CONT"] + cont10
# dedup
seen = set()
new_dedup = []
for t in new_all:
    k = (str(t.get("symbol", "")), str(t.get("entry_date", "")))
    if k in seen:
        continue
    seen.add(k)
    new_dedup.append(t)

print("=== 最终组合验证（所有落地优化）===")
report("原 v20c（VWAP5% 延续）", orig)
report("新 v20c（VWAP10% 延续）", new_dedup)
