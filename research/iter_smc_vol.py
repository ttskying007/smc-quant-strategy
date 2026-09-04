# -*- coding: utf-8 -*-
"""SMC 反转 + 扫损日量能确认：SSL sweep 日放量（真扫损=大资金接筹）vs 缩量"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
import wdh_engine as we
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"


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
        # sweep volume: volume at sweep bar (from seed sweep_date) vs 20d avg
        sweep_date = str(sd.get("sweep_date") or "")
        si = next((k for k, b in enumerate(daily) if b["t"] == sweep_date), None)
        if si is None or si < 20:
            continue
        avg_v = sum(daily[k]["v"] for k in range(si - 20, si)) / 20
        v_ratio = daily[si]["v"] / avg_v if avg_v > 0 else 1
        tr = we.replay_tp2(sd, daily)
        if not tr:
            continue
        rows.append({"entry_date": tr["entry_date"], "v_ratio": v_ratio,
                     "net_pnl_pct": tr["net_pnl_pct"], "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(rows)}", flush=True)
print("SMC 反转 rows:", len(rows))


def report(label, rs):
    if len(rs) < 30:
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


print("\n=== SMC 反转 + 扫损量能 ===")
report("全部", rows)
report("放量扫损(v>1.2x均量)", [r for r in rows if r["v_ratio"] > 1.2])
report("缩量扫损(v<0.8x)", [r for r in rows if r["v_ratio"] < 0.8])
report("放量+缩量排除(0.8-1.2)", [r for r in rows if 0.8 <= r["v_ratio"] <= 1.2])
