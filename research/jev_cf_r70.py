# -*- coding: utf-8 -*-
"""jev_cf_r70.py — 反事实沙盒: S1(CHoCH降权) / S4(rank2降权) 逐年估算"""
import csv, json
from collections import defaultdict

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\jev_full_legs.csv", encoding="utf-8-sig")))


def st(rs, wf=None):
    n = len(rs)
    if not n:
        return n, 0, 0, 0
    p = [float(r["net_pnl_pct"] or 0) for r in rs]
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return n, round(sum(p) / n, 2), round(sum(1 for v in p if v > 0) / n * 100, 1), round(pos / neg, 2) if neg else 999


def rep(name, rs_all, pred):
    base = st(rs_all)
    keep = [r for r in rs_all if pred(r)]
    drop = [r for r in rs_all if not pred(r)]
    print(f"\n## {name}")
    print(f"  全基线   : {base[0]}腿 avg={base[1]}% WR={base[2]}% PF={base[3]}")
    print(f"  留腿     : {keep and len(keep)}腿 avg={st(keep)[1]}% WR={st(keep)[2]}% PF={st(keep)[3]}")
    print(f"  被降权腿 : {drop and len(drop)}腿 avg={st(drop)[1]}% WR={st(drop)[2]}% PF={st(drop)[3]}")
    per_year = defaultdict(lambda: ([], []))
    for r in rs_all:
        y = r["year"]
        (per_year[y][0] if pred(r) else per_year[y][1]).append(r)
    for y in sorted(per_year):
        k, d = per_year[y]
        print(f"    {y}: 留 {st(k)[0]}腿 PF={st(k)[3]}  | 被淘汰 {st(d)[0]}腿 PF={st(d)[3]}")


print("=" * 60)
rep("S1: CHoCH 腿降权(剔除)", rows, lambda r: "CHoCH" not in (r["breakout_kind"] or ""))
print()
rep("S4: rank2 降权(剔除)", rows, lambda r: r["rank"] != "2")
print()
rep("S1+S4 串联", rows, lambda r: "CHoCH" not in (r["breakout_kind"] or "") and r["rank"] != "2")
print()
rep("S5: risk<5% 降权", rows, lambda r: float(r["risk_pct"] or 0) >= 5)
