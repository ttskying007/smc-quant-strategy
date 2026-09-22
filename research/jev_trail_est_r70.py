# -*- coding: utf-8 -*-
"""jev_trail_est_r70.py — S2 止盈改进的代数估算(不动回测引擎)
方法: 利用 mfe_pct / net_pnl_pct, 模拟几种"T+某幅锁定半仓"的出金规则:
  captured = 0.5*min(lock, mfe) + 0.5*net    (半仓在mfe触线时锁定, 另半仓沿用现状)
这是上界近似(假定 mfe 出现的线确实可被锁住), 用于决策是否值得做真回放。
"""
import csv
from collections import defaultdict

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\jev_full_legs.csv", encoding="utf-8-sig")))


def est(lock):
    out = []
    for r in rows:
        mfe = float(r.get("mfe_pct") or 0)
        pnl = float(r["net_pnl_pct"] or 0)
        locked = min(lock, mfe) if mfe > 0 else 0
        new_pnl = 0.5 * locked + 0.5 * pnl
        out.append((r, new_pnl, pnl))
    n = len(out)
    avg_old = sum(p for _, _, p in out) / n
    avg_new = sum(pn for _, pn, _ in out) / n
    wr_old = sum(1 for _, _, p in out if p > 0) / n * 100
    wr_new = sum(1 for _, pn, _ in out if pn > 0) / n * 100
    pf_n = sum(pn for _, pn, _ in out if pn > 0) / max(-sum(pn for _, pn, _ in out if pn < 0), 1e-9)
    return n, avg_old, avg_new, wr_old, wr_new, pf_n


print("| 锁定值% | avg旧 | avg新 | Δ | WR旧 | WR新 | PF新 |")
print("|---|---|---|---|---|---|---|")
for lock in [2, 3, 4, 5, 6, 8, 10]:
    n, ao, an, wo, wn, pf_n = est(lock)
    print(f"| +{lock}% | {ao:.2f} | {an:.2f} | {an-ao:+.2f} | {wo:.1f} | {wn:.1f} | {pf_n:.2f} |")

# 按年细看一个档位
for lock in [3, 5]:
    print(f"\n按年详看 lock=+{lock}%")
    by_y = defaultdict(list)
    for r in rows:
        by_y[r["year"]].append(r)
    for y in sorted(by_y):
        old = sum(float(r["net_pnl_pct"] or 0) for r in by_y[y]) / len(by_y[y])
        new = sum(0.5 * min(lock, float(r.get("mfe_pct") or 0) if float(r.get("mfe_pct") or 0) > 0 else 0)
                  + 0.5 * float(r["net_pnl_pct"] or 0) for r in by_y[y]) / len(by_y[y])
        print(f"  {y}: 旧 {old:+.2f} → 新 {new:+.2f}   Δ {new-old:+.2f}")
