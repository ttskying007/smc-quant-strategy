# -*- coding: utf-8 -*-
"""Signal-sequence timing (user: 按信号发生的时间顺序).
SMC seed has sweep_date/touch_date/reclaim_date/entry_date. Test if sequence
compactness (fewer bars sweep->entry) or completeness affects quality."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

# load seeds (W1D1D4 seeds from tencent? use seeds with dates)
seeds = []
with open(r"E:\test\smc_project\wdh\W1D1D4_seeds.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        k = {kk.lstrip("\ufeff"): v for kk, v in r.items()}
        seeds.append(k)
print("seeds:", len(seeds))

# match seeds to TP2 tencent trades (symbol+entry_date) to get pnl
trades = {}
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades[(r["symbol"], str(r["entry_date"]))] = float(r["net_pnl_pct"])

# for each seed with matching trade, compute sequence timing
def day_diff(a, b):
    # YYYYMMDD diff
    return int(b) - int(a) if a and b else None

rows = []
for sd in seeds:
    key = (sd["symbol"], sd["entry_date"])
    if key not in trades:
        continue
    sweep = str(sd.get("sweep_date") or "")
    touch = str(sd.get("touch_date") or "")
    reclaim = str(sd.get("reclaim_date") or "")
    entry = str(sd.get("entry_date") or "")
    # sequence durations (bars)
    d_sweep_touch = day_diff(sweep, touch)
    d_touch_reclaim = day_diff(touch, reclaim)
    d_reclaim_entry = day_diff(reclaim, entry)
    d_sweep_entry = day_diff(sweep, entry)
    # r20 filter
    r20 = sd.get("r20")
    if r20 == "" or r20 is None:
        continue
    r20 = float(r20)
    if not (0 <= r20 < 0.15):
        continue
    rows.append({"symbol": sd["symbol"], "entry_date": entry, "pnl": trades[key],
                 "d_sweep_entry": d_sweep_entry, "d_sweep_touch": d_sweep_touch,
                 "d_touch_reclaim": d_touch_reclaim, "d_reclaim_entry": d_reclaim_entry,
                 "t1_violation": "False"})
print("matched (r20):", len(rows))


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


print("\n=== 信号序列时长（sweep→entry 天数）===")
valid = [r for r in rows if r["d_sweep_entry"] is not None]
print(f"有序列时长样本: {len(valid)}")
report("基线", valid)
report("紧凑序列 (sweep→entry <= 10天)", [r for r in valid if r["d_sweep_entry"] <= 10])
report("中等 (11-20天)", [r for r in valid if r["d_sweep_entry"] and 11 <= r["d_sweep_entry"] <= 20])
report("长序列 (>20天)", [r for r in valid if r["d_sweep_entry"] and r["d_sweep_entry"] > 20])

# touch->reclaim speed (POI reaction)
print("\n=== POI 反应速度（touch→reclaim 天数）===")
v2 = [r for r in valid if r["d_touch_reclaim"] is not None]
report("快速反应 (touch→reclaim <= 2天)", [r for r in v2 if r["d_touch_reclaim"] <= 2])
report("慢速反应 (>2天)", [r for r in v2 if r["d_touch_reclaim"] and r["d_touch_reclaim"] > 2])
