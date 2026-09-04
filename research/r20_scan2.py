# -*- coding: utf-8 -*-
"""Scan R20 buckets using existing TP2 trades + recompute r20 from kline files (fast)."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\smc_backtest_report")
from smc_gates import check_economic_gate

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["t1_violation"] = str(r.get("t1_violation", "")).lower() in ("true", "1", "yes")
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

cache = {}

def r20_of(symbol, entry_date):
    if symbol not in cache:
        p = os.path.join(KT, symbol.replace(".", "_") + "_daily_800.json")
        if not os.path.exists(p):
            cache[symbol] = []
            return None
        raw = json.load(open(p, encoding="utf-8"))
        closes = []
        for r in raw:
            t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
            if t and r.get("c"):
                closes.append((t, float(r["c"])))
        closes.sort()
        cache[symbol] = closes
    closes = cache[symbol]
    dates = [c[0] for c in closes]
    if entry_date not in dates:
        prev = [d for d in dates if d < entry_date]
        if not prev:
            return None
        i = dates.index(prev[-1])
    else:
        i = dates.index(entry_date) - 1
    if i < 20:
        return None
    return closes[i][1] / closes[i - 20][1] - 1


for t in trades:
    t["r20"] = r20_of(t["symbol"], str(t["entry_date"]))

print("\n=== R20 分桶（已有 TP2 交易）===")
buckets = defaultdict(list)
for t in trades:
    if t["r20"] is None:
        continue
    b = int(t["r20"] * 20) / 20
    buckets[b].append(t)

for b in sorted(buckets):
    rs = buckets[b]
    if len(rs) < 20:
        print(f"  r20∈[{b:.2f},{b+0.05:.2f}): n={len(rs)} (过小)")
        continue
    w = sum(1 for t in rs if t["net_pnl_pct"] > 0)
    avg = sum(t["net_pnl_pct"] for t in rs) / len(rs)
    gp = sum(max(t["net_pnl_pct"], 0) for t in rs)
    gl = abs(sum(min(t["net_pnl_pct"], 0) for t in rs))
    print(f"  r20∈[{b:.2f},{b+0.05:.2f}): n={len(rs)} WR={100*w/len(rs):.1f}% avg={avg:+.2f}% PF={gp/gl if gl else 0:.2f}")

# cumulative ranges
print("\n=== 累计范围 ===")
for lo, hi in [(0, 0.05), (0, 0.10), (0, 0.15), (0, 0.20), (-0.05, 0.10), (-0.05, 0.15), (-0.05, 0.20), (None, None)]:
    if lo is None:
        rs = trades
        label = "全部"
    else:
        rs = [t for t in trades if t["r20"] is not None and lo <= t["r20"] < hi]
        label = f"r20∈[{lo},{hi})"
    if len(rs) < 100:
        print(f"  {label}: n={len(rs)} (过小)")
        continue
    gate = check_economic_gate(rs)
    o = gate["overall"]
    print(f"  {label}: n={o['n']} WR={o['wr']}% avg={o['avg']}% PF={o['pf']} payoff={o['payoff']}")
    for y in ("2024", "2025", "2026"):
        ys = [t for t in rs if str(t["entry_date"]).startswith(y)]
        if ys:
            wy = sum(1 for t in ys if t["net_pnl_pct"] > 0)
            print(f"      {y}: n={len(ys)} WR={100*wy/len(ys):.0f}% avg={sum(t['net_pnl_pct'] for t in ys)/len(ys):+.2f}%")
