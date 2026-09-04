# -*- coding: utf-8 -*-
"""延续腿（MARKUP结构+VWAP5%+固定10日）单维度深化：波动率/回撤深度"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
PIVOT = 3
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
    for i in range(80, len(daily) - 15):
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
        if (daily[entry_idx]["c"] - vw) / vw < 0.05:
            continue
        w20 = daily[entry_idx - 20:entry_idx]
        vol20 = sum((b["h"] - b["l"]) / b["c"] for b in w20) / 20 if len(w20) == 20 else 0
        depth = (daily[i]["l"] / sl_tmp - 1)
        pnl = round((daily[entry_idx + 10]["c"] / ep - 1) * 100 - FEE, 4)
        rows.append({"entry_date": daily[entry_idx]["t"], "vol20": vol20, "depth": depth,
                     "net_pnl_pct": pnl, "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(rows)}", flush=True)
print("rows:", len(rows))


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


print("\n=== 延续腿单维度深化 ===")
report("基线（全部）", rows)
v = sorted(r["vol20"] for r in rows)
vmed = v[len(v) // 2]
report("低波动(vol<中位)", [r for r in rows if r["vol20"] < vmed])
report("高波动(vol>中位)", [r for r in rows if r["vol20"] > vmed])
report("深回撤(depth<-0.015)", [r for r in rows if r["depth"] < -0.015])
report("浅回撤(depth>=-0.005)", [r for r in rows if r["depth"] >= -0.005])
report("低波动+深回撤", [r for r in rows if r["vol20"] < vmed and r["depth"] < -0.015])
