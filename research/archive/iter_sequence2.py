# -*- coding: utf-8 -*-
"""Sequence timing on Tencent data directly (regenerate seeds with sequence features)."""
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
        o, h, l, c = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def day_diff(a, b):
    return int(b) - int(a) if a and b else None


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
        if r20 == "" or r20 is None:
            continue
        if not (0 <= float(r20) < 0.15):
            continue
        tr = we.replay_tp2(sd, daily)
        if not tr:
            continue
        d_sweep_entry = day_diff(sd.get("sweep_date"), sd.get("entry_date"))
        d_touch_reclaim = day_diff(sd.get("touch_date"), sd.get("reclaim_date"))
        rows.append({"symbol": sym, "entry_date": tr["entry_date"], "net_pnl_pct": tr["net_pnl_pct"],
                     "d_sweep_entry": d_sweep_entry, "d_touch_reclaim": d_touch_reclaim,
                     "t1_violation": "False"})
    if n % 1500 == 0:
        print(f"  {n} files, rows {len(rows)}", flush=True)
print(f"rows: {len(rows)}")


def report(label, rs):
    if len(rs) < 80:
        print(f"{label}: n={len(rs)} (过小)"); return
    for t in rs:
        t["t1_violation"] = str(t.get("t1_violation", "")).lower() in ("true", "1", "yes")
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"{label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"    {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")


print("\n=== 信号序列时长（腾讯数据）===")
valid = [r for r in rows if r["d_sweep_entry"] is not None]
report("基线", valid)
report("紧凑 (sweep→entry <= 10天)", [r for r in valid if r["d_sweep_entry"] <= 10])
report("中等 (11-20天)", [r for r in valid if 11 <= r["d_sweep_entry"] <= 20])
report("长 (>20天)", [r for r in valid if r["d_sweep_entry"] > 20])
v2 = [r for r in valid if r["d_touch_reclaim"] is not None]
print("\n=== POI 反应速度 ===")
report("快速 (touch→reclaim <= 2天)", [r for r in v2 if r["d_touch_reclaim"] <= 2])
report("慢速 (>2天)", [r for r in v2 if r["d_touch_reclaim"] > 2])
