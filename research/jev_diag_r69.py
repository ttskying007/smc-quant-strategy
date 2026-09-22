# -*- coding: utf-8 -*-
"""jev_diag_r69.py — R69 多维度病灶诊断 (从 R68 全景 CSV 出表)
维度: 趋势 × 突破型 × 回踩态 × 出场原因 × 组合 × 风险档 × Jev联合
产出研究结论 → 候选手术清单"""
import csv, os
from collections import defaultdict

SRC = r"E:\test\smc_project\research\jev_full_legs.csv"
OUT = r"E:\test\smc_project\research\handover\R69_diagnosis.md"


def st(rows):
    n = len(rows)
    if not n:
        return n, 0, 0, 0
    pnl = [float(r["net_pnl_pct"] or 0) for r in rows]
    avg = sum(pnl) / n
    wr = sum(1 for v in pnl if v > 0) / n * 100
    pos = sum(v for v in pnl if v > 0)
    neg = -sum(v for v in pnl if v < 0)
    return n, round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999


def tab(rows, key, min_n=15, sort_by="n", top=None):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    out = [(k,) + st(v) for k, v in g.items()]
    out = [o for o in out if o[1] >= min_n]
    if sort_by == "n":
        out.sort(key=lambda x: -x[1])
    else:
        out.sort(key=lambda x: x[2])
    if top:
        out = out[:top]
    return out


rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
md = ["# R69 — 病灶诊断(1858 腿)\n", f"总貌: n={len(rows)}, avg=4.07 WR=64.0 PF=3.36\n"]

DIMS = [
    ("D1 趋势状态", lambda r: r["trend_state"]),
    ("D2 突破型", lambda r: r["breakout_kind"]),
    ("D3 回踩状态", lambda r: r["retrace_state"]),
    ("D4 出场原因", lambda r: r["reason"]),
    ("D5 组合名", lambda r: r["combo"]),
    ("D6 src", lambda r: r["src"]),
    ("D7 Jev趋势判定", lambda r: r["j_trend"]),
    ("D8 Jev时机场", lambda r: ("[" + r["j_timing"][0] + "档]") if r["j_timing"] else "-"),
    ("D9 风险档(risk_pct)", lambda r: f"r{float(r['risk_pct'] or 0):.0f}"),
    ("D10 持有天数", lambda r: ("短(≤3)" if int(r["hold_bars"] or 0) <= 3 else "中(4-9)" if int(r["hold_bars"] or 0) <= 9 else "长(10+)")),
    ("D11 rank", lambda r: f"rank{r['rank']}"),
    ("D12 板型", lambda r: r["board"]),
    ("D13 回测年×趋势", lambda r: r["year"] + " " + r["trend_state"]),
]
for title, fn in DIMS:
    md.append(f"\n## {title}\n")
    md.append("| 桶 | n | avg% | WR% | PF |")
    md.append("|---|---|---|---|---|")
    for b in tab(rows, fn):
        md.append(f"| {b[0]} | {b[1]} | {b[2]} | {b[3]} | {b[4]} |")

# 关键交叉
md.append("\n## X1 趋势×回踩态\n| 桶 | n | avg% | WR% | PF |\n|---|---|---|---|---|")
for b in tab(rows, lambda r: f"{r['trend_state']}|{r['retrace_state']}", min_n=10):
    md.append("| " + " | ".join(str(x) for x in b) + " |")

md.append("\n## X2 突破型×回踩态\n| 桶 | n | avg% | WR% | PF |\n|---|---|---|---|---|")
for b in tab(rows, lambda r: f"{r['breakout_kind']}|{r['retrace_state']}", min_n=10):
    md.append("| " + " | ".join(str(x) for x in b) + " |")

md.append("\n## X3 出场原因×持有\n| 桶 | n | avg% | WR% | PF |\n|---|---|---|---|---|")
for b in tab(rows, lambda r: f"{r['reason']}|h{r['hold_bars'] and min(int(r['hold_bars']), 15)}", min_n=15):
    md.append("| " + " | ".join(str(x) for x in b) + " |")

# 吃肉没吃干净 = mfe vs pnl
md.append("\n## X4 '赚没吃到位' 诊断 (mfe - pnl 差值分档)\n")
diffs = []
for r in rows:
    try:
        mfe = float(r["mfe_pct"] or 0)
        p = float(r["net_pnl_pct"] or 0)
        diffs.append((mfe - p, r))
    except Exception:
        pass
md.append("| 漏出幅度 | n | avg mfe | avg pnl |")
md.append("|---|---|---|---|")
for lo, hi, name in [(0, 1, "0-1%(完全到位)"), (1, 3, "1-3%"), (3, 6, "3-6%"), (6, 12, "6-12%"), (12, 99, "12%+(大幅回吐)")]:
    sub = [r for d, r in diffs if lo <= d < hi]
    if sub:
        avg_m = sum(float(r["mfe_pct"] or 0) for r in sub) / len(sub)
        avg_p = sum(float(r["net_pnl_pct"] or 0) for r in sub) / len(sub)
        md.append(f"| {name} | {len(sub)} | {avg_m:.2f} | {avg_p:.2f} |")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R69 → {OUT}")
