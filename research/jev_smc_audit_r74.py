# -*- coding: utf-8 -*-
"""jev_smc_audit_r74.py — R74: 逐 SMC 信号族 × Jev 五问 的审计
数据源: jev_full_legs.csv (R68合成: 引擎链字段 + Jev v2)
做法: 从 chain_json events_tail 提取每条腿所见 SMC 信号类型(bos/choch/ob/fvg/ifvg/lv/ote/sweep),
      以及 last_event_kind; 分组统计 pnl × Jev 判定
产出: handover/R74_smc_signal_audit.md
"""
import csv, json, os, sys, io
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
SRC = r"E:\test\smc_project\research\jev_full_legs.csv"
OUT = r"E:\test\smc_project\research\handover\R74_smc_signal_audit.md"


def st(rs):
    n = len(rs)
    if not n:
        return n, 0, 0, 0, 0
    p = [float(r["net_pnl_pct"] or 0) for r in rs]
    pos = sum(v for v in p if v > 0); neg = -sum(v for v in p if v < 0)
    avgp = sum(float(r.get("j_p_valid") or 0) for r in rs) / n
    return n, round(sum(p) / n, 2), round(sum(1 for v in p if v > 0) / n * 100, 1), \
        round(pos / neg, 2) if neg else 999, round(avgp, 3)


legs = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
md = ["# R74 — 按 SMC 信号族审计(1858 腿)\n"]

# ---- 1. last_event_kind(事件锚) ----
md.append("## A. last_event_kind(引擎事件锚)")
md.append("| 锚 | n | avg% | WR% | PF | Jev p_valid均 |")
md.append("|---|---|---|---|---|---|")
g = defaultdict(list)
for r in legs:
    g[r.get("last_event_kind") or "-"].append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    if len(v) >= 10:
        md.append("| " + " | ".join(str(x) for x in [k, *st(v)]) + " |")

# ---- 2. 信号族出现与否(events_tail 家族) ----
FAMS = {"bos": "BOS", "choch": "CHoCH", "ob": "OB", "fvg": "FVG", "ifvg": "IFVG",
        "lv": "LV/流动性", "ote": "OTE", "eq": "EQH/EQL", "sweep": "Sweep", "brk": "BRK", "rb": "RB"}


def fams_of(r):
    # v22 冻结腿的 events_tail 只含结构事件(BOS/CHoCH, kind 字段); OB/FVG/IFVG 存在于 anchor_note
    # 文本, 不在结构化字段 — 见报告内"族覆盖限制"说明
    try:
        evs = json.loads(r.get("events_tail") or "[]")
    except Exception:
        evs = []
    seen = set()
    for e in evs:
        kind = str(e.get("kind") or e.get("family") or e.get("type") or "").lower()
        if "bos" in kind:
            seen.add("bos")
        elif "choch" in kind:
            seen.add("choch")
    return seen


md.append("\n## B. 腿内 chain events_tail BOS/CHoCH 个数 × 盈亏")
md.append("\n> **族覆盖限制**: v22 冻结腿的 events_tail 只有结构事件 (BOS/CHoCH, 来自 core/chain);")
md.append("> OB/FVG/IFVG 当时只在 anchor_note 文本里, 不是结构化字段。R60 引擎链改造后 signal_family 入 CSV, 下次 v23 冻结时可覆盖全族。\n")
md.append("| 个数 | n | avg% | WR% | PF |")
md.append("|---|---|---|---|---|")
g = defaultdict(list)
for r in legs:
    g[len(fams_of(r))].append(r)
for k in sorted(g):
    md.append("| " + " | ".join(str(x) for x in [f"{k} 种", *st(g[k])[:4]]) + " |")

# ---- 3. 突破型 × Jev 趋势判定的合规度 ----
md.append("\n## C. 突破型 × Jev 趋势判定 合规度")
md.append("| 组合 | n | avg% | WR% | ")
md.append("|---|---|---|---|")
g = defaultdict(list)
for r in legs:
    g[f"{r.get('breakout_kind') or '-'} × jev={r.get('j_trend') or '-'}"].append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:15]:
    if len(v) >= 8:
        n, a, w, p, _ = st(v)
        md.append(f"| {k} | {n} | {a} | {w} |")

# ---- 4. 入场位置质量: 买入价 vs 回踩价/突破价 ----
md.append("\n## D. 入场位置质量(buy vs retrace/breakout 价差)")
md.append("| 价差桶 | n | avg% | WR% |")
md.append("|---|---|---|---|")
g = defaultdict(list)
for r in legs:
    try:
        b = float(r["buy_price"]); rt = float(r["retrace_price"] or 0)
        if rt > 0:
            d = (b - rt) / rt * 100
            g["贴买(差<1%)" if abs(d) < 1 else ("偏上1-3%" if 0 <= d < 3 else ("偏下1-3%" if -3 <= d < 0 else "3%+脱节"))].append(r)
    except Exception:
        pass
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
    n, a, w, _, _ = st(v)
    md.append(f"| {k} | {n} | {a} | {w} |")

# ---- 5. Jev tpsl 判型 × 出场原因(识别 tp 配置错位) ----
md.append("\n## E. Jev TP/SL 判型 × 出场原因交叉(v2 版, 无前视)")
md.append("| 组合 | n | avg% | WR% |")
md.append("|---|---|---|---|")
g = defaultdict(list)
for r in legs:
    g[f"tpsl={r.get('j_tpsl') or 'none'} × exit={r.get('reason') or '-'}"] .append(r)
for k, v in sorted(g.items(), key=lambda kv: -len(kv[1]))[:12]:
    if len(v) >= 10:
        n, a, w, _, _ = st(v)
        md.append(f"| {k} | {n} | {a} | {w} |")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R74 → {OUT}")
