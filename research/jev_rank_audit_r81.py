# -*- coding: utf-8 -*-
"""jev_rank_audit_r81.py — R81: rank 分量级审计
问题: 发现 rank2 倒挂(rank2腿平均 0.76% 而 rank5+ 5%+)。骂的对象不是 rank, 是分量。
做法: 对每个 binary 分量做携带 vs 不携带的 PnL 影响分析;
      再枚举"只有这个分量=1 而其它=0"的分量单打独斗表现
产出: handover/R81_rank_component_audit.md
"""
import csv, json, os, sys, io
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
SRC = r"E:\test\smc_project\research\combo_v22_trades.csv"
OUT = r"E:\test\smc_project\research\handover\R81_rank_component_audit.md"

rows = [r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))]


def st(rs):
    n = len(rs)
    if not n:
        return n, 0, 0, 0
    p = [float(r["net_pnl_pct"] or 0) for r in rs]
    pos = sum(v for v in p if v > 0); neg = -sum(v for v in p if v < 0)
    return n, round(sum(p) / n, 2), round(sum(1 for v in p if v > 0) / n * 100, 1), round(pos / neg, 2) if neg else 999


# 解析 rank_components
for r in rows:
    try:
        r["_rc"] = json.loads(r["rank_components"]) if r.get("rank_components") else {}
    except Exception:
        r["_rc"] = {}

COMPS = ["stage", "vr1", "vr2", "span", "adx", "wt_down", "vol_cont", "etype"]

md = ["# R81 — rank 分量审计(1858腿, 只统计 EVENT/CONT 等带 rc 的)\n"]

# 1. 每分量: 带 vs 不带
md.append("## A. 每分量携带效应(差值 = 有 - 无)")
md.append("| 分量 | 无它 (n/avg/PF) | 有它 (n/avg/PF) | 有-无 avg差 | 判定 |")
md.append("|---|---|---|---|---|")
for c in COMPS:
    no = [r for r in rows if r["_rc"].get(c) == 0]
    yes = [r for r in rows if r["_rc"].get(c) == 1]
    n0, a0, w0, p0 = st(no)
    n1, a1, w1, p1 = st(yes)
    delta = a1 - a0
    verdict = {"stage": "入趋势阶段正确性", "vr1": "v_ratio 档1", "vr2": "v_ratio 档2",
               "span": "阶段持续", "adx": "ADX确认", "wt_down": "周趋势向下", "vol_cont": "量能续", "etype": "事件类型"}.get(c, c)
    md.append(f"| {c} | {n0}/{a0}/{p0} | {n1}/{a1}/{p1} | **{delta:+.2f}** | {verdict} |")

# 2. 只有单个分量 = 1 的腿("单兵作战")
md.append("\n## B. 单兵作战(rank 只有这一个分量为1, 其它为0)")
md.append("| 分量 | n | avg% | WR% | PF |")
md.append("|---|---|---|---|---|")
for c in COMPS:
    solo = [r for r in rows if r["_rc"].get(c) == 1 and sum(v for v in r["_rc"].values() if v) == 1]
    if len(solo) >= 8:
        md.append("| " + " | ".join(str(x) for x in [c, *st(solo)]) + " |")

# 3. 高 rank(4+)里哪个分量最没有增加价值 (leave-one-out)
md.append("\n## C. leave-one-out(只在 rank≥4 腿里缺此分量 vs 有)")
md.append("| 分量 | 缺它的 rank≥4 (n/avg) | 有它的 rank≥4 (n/avg) | 影响 |")
md.append("|---|---|---|---|")
for c in COMPS:
    miss = [r for r in rows if int(r.get("rank") or 0) >= 4 and r["_rc"].get(c) == 0]
    have = [r for r in rows if int(r.get("rank") or 0) >= 4 and r["_rc"].get(c) == 1]
    if miss and have:
        md.append(f"| {c} | {len(miss)}/{st(miss)[1]} | {len(have)}/{st(have)[1]} | {st(have)[1] - st(miss)[1]:+.2f} |")

# 4. rank 数字分解到 rank2 的罪魁祸首
md.append("\n## D. rank2 的病灶定位(是谁在 rank2 里拼命拖)")
md.append("| rank2 腿的分量组合 | n | avg% | WR% |")
md.append("|---|---|---|---|")
g = defaultdict(list)
for r in rows:
    if str(r.get("rank")) == "2":
        key = "+".join(sorted(c for c, v in r["_rc"].items() if v)) or "none"
        g[key].append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    if len(v) >= 5:
        md.append(f"| {k} | {len(v)} | {st(v)[1]} | {st(v)[2]} |")

# 5. 假设: 将 rank 从"组合累加"换成"乘法/权重因子" — 如果删去负分量 rank 分布如何变
md.append("\n## E. 反事实: 如果剔除'贡献为负'的分量(重新算 rank 后)")
neg_comps = []
for c in COMPS:
    no = [r for r in rows if r["_rc"].get(c) == 0]
    yes = [r for r in rows if r["_rc"].get(c) == 1]
    if yes and no and st(yes)[1] < st(no)[1] - 0.5:
        neg_comps.append(c)
md.append(f"贡献<−0.5pp 的分量: **{', '.join(neg_comps) or '无'}**")
if neg_comps:
    md.append("| 筛选 | n | avg% | PF |")
    md.append("|---|---|---|---|")
    keep = [r for r in rows if all(r["_rc"].get(c) != 1 for c in neg_comps)]
    md.append(f"| 剔除含负分量的腿 | {len(keep)} | {st(keep)[1]} | {st(keep)[3]} |")
    md.append(f"| 全基线 | {len(rows)} | {st(rows)[1]} | {st(rows)[3]} |")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R81 → {OUT}")
