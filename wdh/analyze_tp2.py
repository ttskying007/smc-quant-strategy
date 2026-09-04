# -*- coding: utf-8 -*-
import csv, io, sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
trades = []
with open(r"E:\test\smc_project\wdh\TP2_trades.csv", encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh):
        trades.append(r)

# 2026 monthly breakdown
m26 = defaultdict(list)
for t in trades:
    if str(t["entry_date"]).startswith("2026"):
        m26[str(t["entry_date"])[:6]].append(float(t["net_pnl_pct"]))
print("2026 月度:")
for m in sorted(m26):
    rs = m26[m]
    n = len(rs)
    wins = [x for x in rs if x > 0]
    print(f"  {m}: n={n} WR={100*len(wins)/n:.1f}% avg={sum(rs)/n:+.3f}% total={sum(rs):+.1f}%")

# exit reasons by year 2026
r26 = Counter(t["reason"] for t in trades if str(t["entry_date"]).startswith("2026"))
print("\n2026 出场原因:", dict(r26))

# all years exit distribution
print("\n全部出场原因:", dict(Counter(t["reason"] for t in trades)))

# avg win/loss by reason
def stats(rs):
    if not rs: return (0,0,0)
    n=len(rs); w=[x for x in rs if x>0]
    return (n, 100*len(w)/n, sum(rs)/n)
for reason in ("TP2_RUNNER", "SL_HIT", "BE", "TIME_STOP"):
    rs=[float(t["net_pnl_pct"]) for t in trades if t["reason"]==reason]
    n,wr,avg = stats(rs)
    print(f"  {reason}: n={n} WR={wr:.1f}% avg={avg:+.3f}%")
