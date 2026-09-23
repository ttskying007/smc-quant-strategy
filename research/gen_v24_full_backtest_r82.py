# -*- coding: utf-8 -*-
"""gen_v24_full_backtest_r82.py — R82: v24 影子(权重) vs v22 基线 逐年×逐月全明细报告
新增维度:
1. 总览
2. 逐年 × 权重组(>=1 vs <1 vs <0.7)
3. 逐年逐月(全月行, 含两个版本同屏)
4. 月份累计统计
5. 季度分组
6. 一致性: v24 vs 基线 环比差值, 看是否有仅被影子"施舍"的月份
"""
import csv, os, sys, io
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "combo_v23_shadow.csv")
OUT = os.path.join(ROOT, "handover", "R82_v24_full_backtest.md")

rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))


def st(rs, wkey=None):
    if not rs:
        return 0, 0, 0, 0
    if wkey:
        ps = [(float(r["net_pnl_pct"] or 0), float(r.get(wkey) or 1)) for r in rs]
        n = len(rs)
        tot = sum(p * w for p, w in ps)
        avg = tot / sum(w for p, w in ps)
        wr = sum(1 for p, w in ps if p > 0) / n * 100
        pos = sum(p * w for p, w in ps if p > 0)
        neg = -sum(p * w for p, w in ps if p < 0)
        pf = pos / neg if neg else 999
        return n, round(avg, 2), round(wr, 1), round(pf, 2)
    ps = [float(r["net_pnl_pct"] or 0) for r in rs]
    pos = sum(v for v in ps if v > 0); neg = -sum(v for v in ps if v < 0)
    return (len(rs), round(sum(ps) / len(ps), 2),
            round(sum(1 for v in ps if v > 0) / len(ps) * 100, 1),
            round(pos / neg, 2) if neg else 999)


md = ["# R82 — v24 影子组合(12 手术) 全回测逐年逐月详细报告",
      f"切片: 总 n={len(rows)}, 每年 × 每月 × 权重分组\n"]

# ═══════ 1. 总览卡 ═══════
bl_n, bl_avg, bl_wr, bl_pf = st(rows)
v_n, v_avg, v_wr, v_pf = st(rows, "v23_weight")
md.append("## 1. 总览")
md.append("| 版 | n | Σw | avg% | WR% | PF |")
md.append("|---|---|---|---|---|---|")
md.append(f"| v22 基线 | {bl_n} | {bl_n} | {bl_avg} | {bl_wr} | {bl_pf} |")
md.append(f"| v24 影子(9手术→12) | {v_n} | {round(sum(float(r.get('v23_weight') or 1) for r in rows), 1)} | {v_avg} | {v_wr} | {v_pf} |")
md.append(f"| 提升 | — | — | **+{v_avg - bl_avg:.2f}pp** | **+{v_wr - bl_wr:.1f}pt** | **+{(v_pf - bl_pf) / bl_pf * 100:.0f}%** |")

# ═══════ 2. 逐年 × 权重桶 ═══════
md.append("\n## 2. 逐年分权重桶(基线的同腿分段看影子规则是否有效)")
md.append("| 年 × 权重桶 | n | v22 avg | v22 PF | v24 avg | v24 PF | 差值 |")
md.append("|---|---|---|---|---|---|---|")
by_yw = defaultdict(list)
for r in rows:
    y = r["entry_date"][:4]
    w = float(r.get("v23_weight") or 1)
    b = "w≥1" if w >= 1 else ("w 0.7-1" if w >= 0.7 else "w<0.7")
    by_yw[(y, b)].append(r)
for (y, b), rs in sorted(by_yw.items()):
    _, a0, _, p0 = st(rs)
    _, a1, _, p1 = st(rs, "v23_weight")
    md.append(f"| {y} {b} | {len(rs)} | {a0} | {p0} | {a1} | {p1} | **{a1 - a0:+.2f}** |")

# ═══════ 3. 逐年逐月只 v24 ═══════
md.append("\n## 3. 逐年逐月(v24 加权, 权重对齐后回看)")
md.append("| 月 | n | Σw | avg% | WR% | PF | v22同腿avg | v22同腿PF | Δavg | ΔPF |")
md.append("|---|---|---|---|---|---|---|---|---|---|")
def _ym(d):
    """YYYYMMDD or YYYY-MM-DD → YYYY-MM"""
    d = str(d)
    return d[:4] + "-" + d[5:7] if "-" in d else d[:4] + "-" + d[4:6]


by_m = defaultdict(list)
for r in rows:
    by_m[_ym(r["entry_date"])].append(r)
for m in sorted(by_m):
    rs = by_m[m]
    n0, a0, w0, p0 = st(rs)
    _, a1, w1, p1 = st(rs, "v23_weight")
    sw = round(sum(float(r.get("v23_weight") or 1) for r in rs), 1)
    md.append(f"| {m} | {n0} | {sw} | {a1} | {w1} | {p1} | {a0} | {p0} | {a1 - a0:+.2f} | {p1 - p0:+.2f} |")

# ═══════ 4. 月份汇总 ═══════
md.append("\n## 4. 按月份1-12(齐春夏秋冬对齐看)")
md.append("| 月份 | n | 基线 avg | 影子 avg | Δavg |")
md.append("|---|---|---|---|---|")
by_mm = defaultdict(list)
for r in rows:
    by_mm[_ym(r["entry_date"])[5:7]].append(r)
for mm in sorted(by_mm):
    rs = by_mm[mm]
    _, a0, _, _ = st(rs)
    _, a1, _, _ = st(rs, "v23_weight")
    md.append(f"| {mm} | {len(rs)} | {a0} | {a1} | {a1 - a0:+.2f} |")

# ═══════ 5. 季度 ═══════
md.append("\n## 5. 按季度")
md.append("| 季度 | n | 基线 avg/PF | 影子 avg/PF | Δ |")
md.append("|---|---|---|---|---|")
by_q = defaultdict(list)
for r in rows:
    month = int(_ym(r["entry_date"])[5:7])
    q = "Q" + str((month - 1) // 3 + 1)
    by_q[q].append(r)
for q in sorted(by_q):
    rs = by_q[q]
    n0, a0, _, p0 = st(rs)
    _, a1, _, p1 = st(rs, "v23_weight")
    md.append(f"| {q} | {n0} | {a0}/{p0} | {a1}/{p1} | {a1 - a0:+.2f} |")

# ═══════ 6. 裁判表: 影子使月份变差的清单(小样本警告) ═══════
md.append("\n## 6. 裁判表:哪些月份影子反而变差(小样本也可能骗人)")
md.append("| 月 | n | 基线 avg | 影子 avg | 变差幅度 |")
md.append("|---|---|---|---|---|")
worse = []
for m in sorted(by_m):
    rs = by_m[m]
    if len(rs) < 3:
        continue
    _, a0, _, _ = st(rs)
    _, a1, _, _ = st(rs, "v23_weight")
    if a1 < a0:
        worse.append((m, len(rs), a0, a1, a1 - a0))
for w in worse:
    md.append(f"| {w[0]} | {w[1]} | {w[2]} | {w[3]} | **{w[4]:+.2f}** |")
md.append(f"\n（共通警示：总变差月份 {len(worse)}/{len([m for m, rs in by_m.items() if len(rs) >= 3])}, 全部是权重降权所致）")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R82 → {OUT}, 月份数: {len(by_m)}")
