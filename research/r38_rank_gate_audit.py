# -*- coding: utf-8 -*-
"""r38_rank_gate_audit.py —— 对**已接线的生产改动**应用新学的 R22/R21 审计.

背景: R38ac 已把 rank_prod>=3 门槛接线到生产 paper_sim。
R38ap 新沉淀了 R22(覆盖率检验)与 R21(层内增量)。
**本轮把这些新规则反过来施加到我自己已交付的改动上** —— 若 rank 门槛也有
"覆盖率极端不均"或"只是共同因子代理"的问题, 必须诚实标注甚至回滚。

检验:
  ① 逐年覆盖率: rank_prod>=3 门槛在每年的命中率
     (R22 判据: 若相差一个数量级 -> 单一事件拟合)
  ② 逐年增量: 各年 门槛内 vs 门槛外 的 avg 差
  ③ 层内检验: 固定"全市场增持强度"后, rank 门槛是否仍有增量
     (R21 判据: 若增量消失 -> rank 只是市场强度的代理)
  ④ IS/OOS 覆盖率对照

判据(预注册):
  · 若某年命中率 < 5% 或 > 90% -> 标注 regime 依赖
  · 若层内增量消失 -> 严重问题, 建议回滚

纯研究, 不修改生产(仅审计)。
"""
import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = r"E:\test\smc_project\research"
IS_END = "20250630"
YEARS = ("2023", "2024", "2025", "2026")


def f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


# rank_prod 已在 r38_rank_chain_cands.json 中(cap 前全集, 含生产 9 特征 rank)
p = os.path.join(HERE, "r38_rank_chain_cands.json")
if not os.path.exists(p):
    print("缺 r38_rank_chain_cands.json —— 需先跑 r38_rank_chain.py")
    sys.exit(1)
cands = json.load(open(p, encoding="utf-8"))
print("=" * 96)
print("对已接线生产改动(rank_prod>=3)的 R21/R22 反向审计")
print("=" * 96)
print("候选(cap 前) n=%d" % len(cands))


def stats(rows):
    if not rows:
        return None
    v = [r["net"] for r in rows]
    w = [x for x in v if x > 0]
    l = [x for x in v if x <= 0]
    pf = sum(w) / abs(sum(l)) if sum(l) else 99.0
    return {"n": len(v), "avg": round(sum(v) / len(v), 2),
            "wr": round(100 * len(w) / len(v), 1), "pf": round(pf, 2)}


# ══ ① 逐年覆盖率(R22) ══
print("\n" + "=" * 96)
print("① 逐年覆盖率(R22 判据: 相差一个数量级 => 单一事件拟合)")
print("=" * 96)
print("%-8s %8s %8s %10s %18s %18s" % ("年", "总数", "过门槛", "命中率", "门槛内", "门槛外"))
cov = {}
for y in YEARS:
    rs = [r for r in cands if str(r["d"])[:4] == y]
    if not rs:
        continue
    hit = [r for r in rs if r["rank"] >= 3]
    miss = [r for r in rs if r["rank"] < 3]
    rate = 100 * len(hit) / len(rs)
    cov[y] = rate
    sh, sm = stats(hit), stats(miss)
    ch = "%d %+.2f%%/%.2f" % (sh["n"], sh["avg"], sh["pf"]) if sh else "—"
    cm = "%d %+.2f%%/%.2f" % (sm["n"], sm["avg"], sm["pf"]) if sm else "—"
    print("%-8s %8d %8d %9.1f%% %18s %18s" % (y, len(rs), len(hit), rate, ch, cm))

if cov:
    lo, hi = min(cov.values()), max(cov.values())
    print("\n  命中率范围: %.1f%% (min %s) ~ %.1f%% (max %s)"
          % (lo, min(cov, key=cov.get), hi, max(cov, key=cov.get)))
    ratio = hi / lo if lo > 0 else float("inf")
    print("  极差比: %.1fx" % ratio)
    if ratio >= 3:
        print("  → ⚠ **覆盖率不均(>=3x)** —— 需标注 regime 依赖")
    else:
        print("  → ✅ 覆盖率相对均匀(<3x), 非单一事件拟合")

# ══ ② 逐年增量 ══
print("\n" + "=" * 96)
print("② 逐年增量(门槛内 avg - 门槛外 avg)")
print("=" * 96)
pos_years = 0
for y in YEARS:
    rs = [r for r in cands if str(r["d"])[:4] == y]
    if not rs:
        continue
    hit = [r for r in rs if r["rank"] >= 3]
    miss = [r for r in rs if r["rank"] < 3]
    sh, sm = stats(hit), stats(miss)
    if sh and sm:
        d = sh["avg"] - sm["avg"]
        if d > 0:
            pos_years += 1
        print("  %s: 门槛内 %+.2f%% | 门槛外 %+.2f%% → 增量 %+.2fpp %s"
              % (y, sh["avg"], sm["avg"], d, "✓" if d > 0 else "✗"))
print("  → %d/%d 年增量为正" % (pos_years, len(YEARS)))

# ══ ③ 层内检验(R21): 固定全市场增持强度 ══
print("\n" + "=" * 96)
print("③ 层内检验(R21): 固定全市场增持强度后, rank 门槛是否仍有增量")
print("=" * 96)
import datetime as dt


def d2(s):
    s = str(s).replace("-", "")[:8]
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except Exception:
        return None


for r in cands:
    r["_d"] = d2(r["d"])
    r["_t"] = r.get("net", r.get("net_pnl_pct"))

usable = [r for r in cands if r["_d"] is not None]
# 全市场强度: 同日全部候选数(用日期直方图, 避免 O(n^2))
daycnt = Counter(r["_d"] for r in usable)
for r in usable:
    r["_mkt"] = daycnt[r["_d"]]

print("  全市场强度(同日候选数)分层 × rank 门槛:")
print("  %-16s %-14s %6s %10s %8s" % ("mkt 层", "rank 层", "n", "avg%", "PF"))
MKT_B = [(1, 3), (4, 10), (11, 30), (31, 999)]
for mlo, mhi in MKT_B:
    sub = [r for r in usable if mlo <= r["_mkt"] <= mhi]
    if len(sub) < 30:
        continue
    for lab, cond in (("rank>=3", lambda r: r["rank"] >= 3),
                      ("rank<3", lambda r: r["rank"] < 3)):
        g = [r for r in sub if cond(r)]
        s = stats(g)
        if s and s["n"] >= 10:
            print("  %-16s %-14s %6d %+9.2f%% %8.2f"
                  % ("[%d,%d]" % (mlo, mhi), lab, s["n"], s["avg"], s["pf"]))
    print("  " + "-" * 60)

# ══ ④ IS/OOS 覆盖率 ══
print("\n" + "=" * 96)
print("④ IS/OOS 覆盖率对照")
print("=" * 96)
for lab, lo, hi in (("IS", "0", IS_END), ("OOS", IS_END + "1", "99999999")):
    rs = [r for r in usable if lo <= str(r["d"]) <= hi]
    if not rs:
        continue
    hit = [r for r in rs if r["rank"] >= 3]
    sh, sa = stats(hit), stats(rs)
    print("  %-4s 全体 n=%4d avg=%+.2f%% | 过门槛 n=%3d (%.0f%%) avg=%+.2f%% PF=%.2f"
          % (lab, sa["n"], sa["avg"], sh["n"], 100 * sh["n"] / sa["n"], sh["avg"], sh["pf"]))

print("\n" + "=" * 96)
print("裁定")
print("=" * 96)
print("  若①覆盖率<3x ②逐年增量多数为正 ③层内增量仍存在 → 已接线改动稳健")
print("  若任一不满足 → 诚实标注, 必要时建议回滚")