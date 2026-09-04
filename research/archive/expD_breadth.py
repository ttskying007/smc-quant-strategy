# -*- coding: utf-8 -*-
"""Experiment D: market breadth filter (advance/decline ratio).
Only trade when equal-weight advance ratio (20-day avg of % stocks up) >= threshold.
Test thresholds 0.45/0.50/0.55 for cross-year consistency."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research"

import random
random.seed(42)
files = sorted(os.listdir(KT))[:]
sample = random.sample(files, min(500, len(files)))

# daily advance ratio: % of sample stocks with positive return that day
day_up = defaultdict(lambda: [0, 0])  # date -> [up_count, total]
for f in sample:
    raw = json.load(open(os.path.join(KT, f), encoding="utf-8"))
    prev = None
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        c = float(r.get("c") or 0)
        if t and c and prev:
            day_up[t][0] += 1 if c > prev else 0
            day_up[t][1] += 1
        if t and c:
            prev = c
breadth = {t: up / tot for t, (up, tot) in day_up.items() if tot >= 50}
dates = sorted(breadth)
# 20-day avg breadth (smoothed, pre-entry)
b20 = {}
for i, t in enumerate(dates):
    if i >= 20:
        b20[t] = sum(breadth[dates[j]] for j in range(i - 19, i + 1)) / 20
print("breadth days:", len(breadth), "b20 days:", len(b20))

trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

def breadth_at(entry_date):
    # breadth at previous trading day (pre-entry)
    if entry_date not in breadth:
        # find previous date
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        entry_date = prev[-1]
    return b20.get(entry_date)

for th in (None, 0.45, 0.50, 0.55):
    if th is None:
        rs = trades
        label = "全部"
    else:
        rs = [t for t in trades if (breadth_at(t["entry_date"]) or 0) >= th]
        label = f"宽度>={th}"
    print(f"\n=== {label}: n={len(rs)} ===")
    if len(rs) < 300:
        print("  n 过小"); continue
    gate = check_economic_gate(rs)
    for c in gate["checks"][:4]:
        print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"  {y}: n={len(ys)} WR={100*w/len(ys):.1f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.3f}%")
