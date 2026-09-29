# -*- coding: utf-8 -*-
"""jev_deep_scan_r75.py — R75: 未审计维度地毯式扫描
目标: 从 R68 CSV 的所有未用过字段里挖出"可能的大质量提升"问题
字段: zone_90d / sl_below_structure / broken_low_level / supply_layers / nearest_supply_dist
      adx_span / stage_span / event_gap_bars / r20 / rank_components / mae_r / mfe_r / hold_bars
      sub_signals出现频×pnl
"""
import csv, os, re, sys, io
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
SRC = r"E:\test\smc_project\research\jev_full_legs.csv"
OUT = r"E:\test\smc_project\research\handover\R75_deep_scan.md"

rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))


def st(rs):
    n = len(rs)
    if not n:
        return n, 0, 0, 0
    p = [float(r["net_pnl_pct"] or 0) for r in rs]
    pos = sum(v for v in p if v > 0); neg = -sum(v for v in p if v < 0)
    return n, round(sum(p) / n, 2), round(sum(1 for v in p if v > 0) / n * 100, 1), round(pos / neg, 2) if neg else 999


def bucketize(row, num_field, cuts):
    try:
        v = float(row.get(num_field) or 0)
    except Exception:
        return "NA"
    for hi, name in cuts:
        if v < hi:
            return name
    return f">={cuts[-1][0]}+"


md = ["# R75 — 未审计维度地毯式扫描 (1858 腿)", "前置已审计: 趋势/突破型/回踩/出场/组合/rank/板/support/jev(不问)\n"]

SCANS = [
    ("zone_90d(90日盘中位置)", lambda r: str(r.get("zone_90d"))),
    ("sl_below_structure(止损位在结构线下?)", lambda r: str(r.get("sl_below_structure"))),
    ("broken_low_level", lambda r: str(r.get("broken_low_level"))),
    ("supply_layers(供给层数)", lambda r: str(r.get("supply_layers"))),
    ("nearest_supply_dist(最近供给距离%)", lambda r: bucketize(r, "nearest_supply_dist", [(2, "<2%"), (4, "2-4%"), (8, "4-8%"), (16, "8-16%")])),
    ("adx_span(ADX持续时间)", lambda r: bucketize(r, "adx_span", [(3, "<3"), (7, "3-7"), (14, "7-14"), (30, "14-30")])),
    ("stage_span(阶段持续bar)", lambda r: bucketize(r, "stage_span", [(10, "<10"), (20, "10-20"), (40, "20-40"), (60, "40-60")])),
    ("event_gap_bars(事件到今天)", lambda r: bucketize(r, "event_gap_bars", [(2, "<2"), (5, "2-5"), (10, "5-10"), (20, "10-20")])),
    ("r20(20日热度)", lambda r: bucketize(r, "r20", [(2, "<2"), (5, "2-5"), (10, "5-10"), (30, "10-30")])),
    ("hold_bars(持仓bar)", lambda r: bucketize(r, "hold_bars", [(2, "<2"), (4, "2-4"), (7, "4-7"), (12, "7-12")])),
    ("mae_r(最大回撤/risk倍数)", lambda r: bucketize(r, "mae_r", [(0.1, "0-0.1"), (0.3, "0.1-0.3"), (0.6, "0.3-0.6"), (1.1, "0.6-1.1")])),
    ("mfe_r(最大浮盈/risk倍数)", lambda r: bucketize(r, "mfe_r", [(0.5, "<0.5"), (1.0, "0.5-1.0"), (2.0, "1.0-2.0"), (4.0, "2.0-4.0")])),
]

for title, fn in SCANS:
    g = defaultdict(list)
    for r in rows:
        g[fn(r)].append(r)
    md.append(f"\n## {title}")
    md.append("| 桶 | n | avg% | WR% | PF |")
    md.append("|---|---|---|---|---|")
    for k, v in sorted(g.items(), key=lambda kv: -st(kv[1])[2]):
        if len(v) >= 15:
            md.append("| " + " | ".join(str(x) for x in [k, *st(v)]) + " |")

# sub_signals 频次×pnl
md.append("\n## 子信号频次(前6) × pnl")
md.append("| sub_signals 头部 | n | avg% | WR% |")
md.append("|---|---|---|---|")
g = defaultdict(list)
for r in rows:
    parts = (r.get("sub_signals") or "").split()[:2]
    g[" ".join(parts) or "none"].append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:12]:
    if len(v) >= 15:
        md.append("| " + " | ".join(str(x) for x in [k, *st(v)[:3]]) + " |")

# rank_components — 补 rank 内部哪些维度在做事
md.append("\n## rank_components 分布")
md.append("| 成分 | 出现次数 | 截取出来 |")
md.append("|---|---|---|")
g = defaultdict(list)
for r in rows:
    s = (r.get("rank_components") or "").strip()
    g[s or "none"].append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:15]:
    md.append(f"| {k} | {len(v)} | avg {st(v)[1]} / PF {st(v)[3]} |")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R75 → {OUT}")
