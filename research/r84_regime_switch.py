# -*- coding: utf-8 -*-
"""r84_regime_switch.py — R84: 市道开关(牛/熊/振荡 detect→子集启动)
regime 判定 (仅用到入场日当日及以前上证数据, 无前视):
  - ret20 = 上证20日收益
  - ret50 = 上证50日收益
  - 牛: ret20≥+1.5% 且 ret50≥+3%
  - 熊: ret20≤−1.5% 且 ret50≤−3%
  - 振荡: 其它
然后:
  A. 每 regime × 基线/影子 数据
  B. 每 regime × 手术桶(s13 flag 情况) 看谁咬人
  C. 每 regime 启用最优子集的反事实 v25
产出: handover/R84_regime_switch.md
"""
import csv, json, os, sys, io
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "combo_v23_shadow.csv")
IDX = os.path.join(ROOT, "idx_sh000001.json")
OUT = os.path.join(ROOT, "handover", "R84_regime_switch.md")

idx = json.load(open(IDX, encoding="utf-8"))
rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
for r in rows:
    r["_pnl"] = float(r["net_pnl_pct"] or 0)
    r["_w"] = float(r.get("v23_weight") or 1)


def idx_at(d):
    d = str(d).replace("-", "")
    j = -1
    for i in range(len(idx) - 1, -1, -1):
        if str(idx[i]["t"]) <= d:
            j = i
            break
    return j


def regime(d):
    j = idx_at(d)
    if j < 50:
        return "probe"
    r20 = (float(idx[j]["c"]) / float(idx[j - 20]["c"]) - 1) * 100
    r50 = (float(idx[j]["c"]) / float(idx[j - 50]["c"]) - 1) * 100
    if r20 >= 1.5 and r50 >= 3:
        return "bull"
    if r20 <= -1.5 and r50 <= -3:
        return "bear"
    return "range"


for r in rows:
    r["_regime"] = regime(r["entry_date"])


def st(rs, wkey=None):
    if not rs:
        return 0, 0, 0, 0
    n = len(rs)
    if wkey:
        tot = sum(r["_pnl"] * r[wkey] for r in rs)
        ws = sum(r[wkey] for r in rs)
        avg = tot / ws if ws else 0
        pos = sum(r["_pnl"] * r[wkey] for r in rs if r["_pnl"] > 0)
        neg = -sum(r["_pnl"] * r[wkey] for r in rs if r["_pnl"] < 0)
    else:
        avg = sum(r["_pnl"] for r in rs) / n
        pos = sum(r["_pnl"] for r in rs if r["_pnl"] > 0)
        neg = -sum(r["_pnl"] for r in rs if r["_pnl"] < 0)
    return n, round(avg, 2), round(sum(1 for r in rs if r["_pnl"] > 0) / n * 100, 1), round(pos / neg, 2) if neg else 999


md = ["# R84 — 市道开关(牛/熊/振荡)", "regime 判定: 上证 ret20≥1.5% 且 ret50≥3% = 牛; ret20≤−1.5% 且 ret50≤−3% = 熊; 其它 = 振荡\n"]

# ═══════ A. 每 regime × 基线/影子 ═══════
md.append("## A. 每 regime × 基线/影子")
md.append("| regime | n | 基线 avg | 基线 PF | 影子 avg | 影子 PF | 升降 |")
md.append("|---|---|---|---|---|---|---|")
by_g = defaultdict(list)
for r in rows:
    by_g[r["_regime"]].append(r)
for g in ("bull", "range", "bear", "probe"):
    rs = by_g.get(g, [])
    if not rs:
        continue
    n0, a0, w0, p0 = st(rs)
    _, a1, w1, p1 = st(rs, "_w")
    md.append(f"| {g} | {n0} | {a0} | {p0} | {a1} | {p1} | **{a1 - a0:+.2f}pp / PF {p1 - p0:+.2f}** |")

# 每 regime × 年
md.append("\n### A2. regime × 年")
md.append("| regime | 年 | n | 基线 avg | 影子 avg |")
md.append("|---|---|---|---|---|")
for g in ("bull", "range", "bear"):
    for y in ("2023", "2024", "2025", "2026"):
        rs = [r for r in rows if r["_regime"] == g and r["entry_date"][:4] == y]
        if rs:
            md.append(f"| {g} | {y} | {len(rs)} | {st(rs)[1]} | {st(rs, '_w')[1]} |")

# ═══════ B. 每 regime 哪些手术桶咬人 ═══════
md.append("\n## B. 每 regime × 主要手术桶(对退场腿拉低原因定位)")
md.append("| regime × flag | n | 基线 avg | 影子 avg | 判定 |")
md.append("|---|---|---|---|---|")
top_flags = ["s1_choch", "s7_up_trend", "s8_sweep_bear", "s10_in_ob", "s12_in_ote", "s13_rank"],
for g in ("bull", "range", "bear"):
    for pf_ in top_flags[0]:
        rs = [r for r in rows if r["_regime"] == g and pf_ in r["v23_flags"]]
        if len(rs) >= 8:
            md.append("| " + " | ".join(str(x) for x in [f"{g} × {pf_}", len(rs), st(rs)[1], st(rs, '_w')[1], ""]) + " |")
md.append("\n(注: 影子对方向, 但手术作用力本就该体现在同桶内)")

# ═══════ C. v25 反事实: regime → 专用子集 ═══════
md.append("\n## C. v25 反事实: regime 路由不同子集")
# 在每 regime 里寻找最优 flag 组 (全修改: 尝试4种路线)
# 路线一: 振荡市千, 不许 untagged (w=1)腿跟 bull 腿, 只靠有 whale/源BRIGADE 的进场
# 简化: 每 regime 加权 tune — range 档 w<0.7 腿全弃(流失), bear 档只留腿数长腿正则加权
def cf_variant(rs, name):
    """反事实函数: 根据不同 regime 改变像素权重"""
    tot = 0
    pos = 0
    neg = 0
    for r in rs:
        # v25 = regime-aware reweight
        w = r["_w"]
        g = r["_regime"]
        m = 1
        if g == "range":
            # 弱市: 对 weight<0.7 的腿直接 ×0.3 (宁可错过)
            m = 0.3 if r["_w"] < 0.7 else 1.0
        elif g == "bear":
            # 熊市: 保守, s1/s4/s13 的腿既然已由下фов上线在出口
            m = 0.5
        tot += r["_pnl"] * w * m
        if r["_pnl"] > 0:
            pos += r["_pnl"] * w * m
        else:
            neg += -r["_pnl"] * w * m
    n2 = len(rs)
    return n2, round(tot / sum(r["_w"] for r in rs) if sum(r["_w"] for r in rs) else 0, 2), round(pos / neg, 2) if neg else 999


n0, a0, _, p0 = st(rows, "_w")
md.append("| 版本 | n | avg | PF |")
md.append("|---|---|---|---|")
md.append(f"| 基线 | {len(rows)} | {st(rows)[1]} | {st(rows)[3]} |")
md.append(f"| v24 (S1-S14) | {n0} | {a0} | {p0} |")

# v25 各 regime 详细
md.append(f"| v25 反事实(振荡×0.3/熊市×0.5 弱化低权重) | {cf_variant(rows, 'v25')[0]} | {cf_variant(rows, 'v25')[1]} | **{cf_variant(rows, 'v25')[2]}** |")

md.append(f"\n### C2. v25 逐年")
md.append("| 年 | v22 平均 | v24 平均 | v25 平均 |")
md.append("|---|---|---|---|")
for y in ("2023", "2024", "2025", "2026"):
    rs = [r for r in rows if r["entry_date"][:4] == y]
    _, a0, _, _ = st(rs)
    _, a1, _, _ = st(rs, "_w")
    n2, a2, _ = cf_variant(rs, "v25")
    md.append(f"| {y} | {a0} | {a1} | {a2} |")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R84 → {OUT}, regime 分布: {[(g, len(by_g[g])) for g in ('bull','range','bear','probe')]}")
