# -*- coding: utf-8 -*-
"""Experiment B: regime filter for cross-year consistency.
Use market breadth (equal-weight 500-stock 20-day average return) as regime indicator.
Test: TP2 trades filtered by 'market in uptrend' vs unfiltered, yearly breakdown."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research"

# build market breadth series (equal-weight 500-stock close index)
import random
random.seed(42)
files = sorted(os.listdir(KT))[:]
sample = random.sample(files, min(500, len(files)))
market_idx = {}  # date -> equal-weight index level
level = {}
for f in sample:
    raw = json.load(open(os.path.join(KT, f), encoding="utf-8"))
    prev = None
    for r in raw:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        c = float(r.get("c") or 0)
        if t and c:
            level[t] = level.get(t, []) + [c]
for t in sorted(level):
    market_idx[t] = sum(level[t]) / len(level[t])
dates = sorted(market_idx)
# 20-day simple MA of index
ma20 = {}
for i, t in enumerate(dates):
    if i >= 20:
        ma20[t] = sum(market_idx[dates[j]] for j in range(i - 19, i + 1)) / 20
print("market index days:", len(dates), "ma20 days:", len(ma20))

# load TP2 trades (tencent version)
trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)
print("TP2 trades:", len(trades))

# tag each trade with regime at entry: index > ma20 (uptrend) vs below (downtrend)
def regime_at(entry_date):
    # use market state at entry-1 (prev day) to avoid using entry day info
    idx = dates.index(entry_date) if entry_date in dates else None
    if idx is None or idx == 0:
        return None
    prev_date = dates[idx - 1]
    m = ma20.get(prev_date)
    if m is None:
        return None
    return "UP" if market_idx[prev_date] > m else "DOWN"

for t in trades:
    t["regime"] = regime_at(t["entry_date"])

def year_of(t):
    return str(t["entry_date"])[:4]

for label, filt in [("全部", lambda t: True), ("仅UP", lambda t: t.get("regime") == "UP"),
                    ("仅DOWN", lambda t: t.get("regime") == "DOWN")]:
    rs = [t for t in trades if filt(t)]
    print(f"\n=== {label}: n={len(rs)} ===")
    if not rs:
        continue
    gate = check_economic_gate(rs)
    for c in gate["checks"][:4]:
        print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
    for y in ("2023", "2024", "2025", "2026"):
        ys = [t for t in rs if year_of(t) == y]
        if ys:
            w = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            avg = sum(t["net_pnl_pct"] for t in ys) / len(ys)
            print(f"  {y}: n={len(ys)} WR={100*w/len(ys):.1f}% avg={avg:+.3f}%")
