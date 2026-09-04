# -*- coding: utf-8 -*-
"""Deep-dive 2026 TP2 failures: signal vs execution, market-state context."""
import csv, io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

trades = []
with open(r"E:\test\smc_project\wdh\TP2_tencent_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        r["net_pnl_pct"] = float(r["net_pnl_pct"])
        trades.append(r)

t26 = [t for t in trades if str(t["entry_date"]).startswith("2026")]
print("2026 trades:", len(t26))

# exit reason breakdown for 2026 vs 2025
from collections import Counter
for y in ("2024", "2025", "2026"):
    ys = [t for t in trades if str(t["entry_date"]).startswith(y)]
    print(f"\n{y}: n={len(ys)}")
    print("  exit:", dict(Counter(t["reason"] for t in ys)))
    for reason in ("TP2_RUNNER", "SL_HIT", "BE", "TIME_STOP"):
        rs = [t for t in ys if t["reason"] == reason]
        if rs:
            w = sum(1 for t in rs if t["net_pnl_pct"] > 0)
            print(f"    {reason}: n={len(rs)} avg={sum(t['net_pnl_pct'] for t in rs)/len(rs):+.2f}%")

# 2026 monthly entry distribution
m26 = defaultdict(list)
for t in t26:
    m26[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])
print("\n2026 月度 entry 分布:")
for m in sorted(m26):
    rs = m26[m]
    w = sum(1 for x in rs if x > 0)
    print(f"  {m}: n={len(rs)} WR={100*w/len(rs):.0f}% avg={sum(rs)/len(rs):+.2f}%")

# entry month vs market regime (from expB: 2026 Mar/May/Jun/Jul down)
print("\n2026 信号入场月 vs 市场: 3月(-9.4%) 5月(-4.1%) 6月(-3.8%) 7月(-8.4%) 为全市场下跌月")
