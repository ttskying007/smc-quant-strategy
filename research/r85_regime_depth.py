# -*- coding: utf-8 -*-
"""r85_regime_depth.py — R85/86: 熊市持续时间分层 + 生产新跑影子审计 + 大盘宽度(breadth)
A: tendency基于上证"连续处于熊 regime 的自然日数"分层
   bear_streak = 入场日往前连续 regime=bear 的交易轴天数
B: 板块广度 breadth = 所有缓存股中 close>MA20 的比例 — 每原则按周采样优良质量
C: R86 生产挂单的 v23 影子标签 + Jev 判定审计(到今天截止)
"""
import csv, json, os, sys, io, glob
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "combo_v23_shadow.csv")
IDX = os.path.join(ROOT, "idx_sh000001.json")
OUT = os.path.join(ROOT, "handover", "R85_regime_depth.md")

idx = json.load(open(IDX, encoding="utf-8"))
rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
for r in rows:
    r["_w"] = float(r.get("v23_weight") or 1)


# ─── 趋势regime预计算 ───
def regime_at_j(j):
    if j < 50:
        return "probe"
    r20 = (float(idx[j]["c"]) / float(idx[j - 20]["c"]) - 1) * 100
    r50 = (float(idx[j]["c"]) / float(idx[j - 50]["c"]) - 1) * 100
    if r20 >= 1.5 and r50 >= 3:
        return "bull"
    if r20 <= -1.5 and r50 <= -3:
        return "bear"
    return "range"


regime_by_idx = [regime_at_j(j) for j in range(len(idx))]

# 每天入(以自然日看 bear 的连续 bar 数)
bear_streak = [0] * len(idx)
for j in range(len(idx)):
    if regime_by_idx[j] == "bear":
        bear_streak[j] = bear_streak[j - 1] + 1 if j > 0 else 1


def bear_streak_at(d):
    d = str(d).replace("-", "")
    j = -1
    for i in range(len(idx) - 1, -1, -1):
        if str(idx[i]["t"]) <= d:
            j = i
            break
    return bear_streak[j] if j >= 0 else 0


def st(rs, wkey=None):
    if not rs:
        return 0, 0, 0, 0
    n = len(rs)
    ps = [(float(r["net_pnl_pct"] or 0), float(r.get(wkey) or 1)) for r in rs]
    if wkey:
        tot = sum(p * w for p, w in ps); ws = sum(w for p, w in ps)
        avg = tot / ws; pos = sum(p * w for p, w in ps if p > 0); neg = -sum(p * w for p, w in ps if p < 0)
    else:
        ps2 = [p for p, w in ps]
        avg = sum(ps2) / n; pos = sum(v for v in ps2 if v > 0); neg = -sum(v for v in ps2 if v < 0)
    wr = sum(1 for p, w in ps if p > 0) / n * 100
    return n, round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999


md = ["# R85 — 熊市持续时间分层 + 市场宽度(基于 index 全历史)",
      "bear_streak = 入场日往前, 上证连处于 bear regime 的连续 bar 数\n"]

# ─── A. bear 时间分层 ───
for r in rows:
    r["_bs"] = bear_streak_at(r["entry_date"])

md.append("## A. 熊市持续时间分层(bear_streak 桶)")
md.append("| bear_streak (bar) | n | v22 avg | v22 PF | v24 avg | v24 PF |")
md.append("|---|---|---|---|---|---|")
by_b = defaultdict(list)
for r in rows:
    s = r["_bs"]
    if s == 0:
        b = "非熊市"
    elif s < 15:
        b = "熊<15bar(早期)"
    elif s < 30:
        b = "熊15-30(加速)"
    elif s < 60:
        b = "熊30-60(中期)"
    else:
        b = "熊>60(晚期)"
    by_b[b].append(r)
for b in ("非熊市", "熊<15bar(早期)", "熊15-30(加速)", "熊30-60(中期)", "熊>60(晚期)"):
    rs = by_b.get(b, [])
    if rs:
        n0, a0, _, p0 = st(rs)
        _, a1, _, p1 = st(rs, "_w")
        md.append(f"| {b} | {n0} | {a0} | {p0} | {a1} | {p1} |")

# ─── B. 大盘广度(breadth) — 上周数据可模拟 ───
md.append("\n## B. 大盘宽度(全市场 close>MA20 的比例)")
md.append("说明: 用缓存 2947 只会全计算太贵. 采样 N=120 只 ETF/+随机组合, 生成周宽度表.")
KC = os.path.normpath(os.path.join(ROOT, "..", "hermes", "kline_cache_tencent"))
files = glob.glob(os.path.join(KC, "*_daily_800.json"))
import random
random.seed(42)
sample_files = random.sample(files, 120)
breadth_by_date = defaultdict(lambda: [0, 0])
for fp in sample_files:
    try:
        bars = json.load(open(fp, encoding="utf-8"))
        closes = [(str(b["t"]), float(b["c"])) for b in bars]
        for i in range(20, len(closes)):
            ma20 = sum(c for _, c in closes[i - 20:i]) / 20
            above = 1 if closes[i][1] > ma20 else 0
            breadth_by_date[closes[i][0]][0] += above
            breadth_by_date[closes[i][0]][1] += 1
    except Exception:
        pass


def breadth_pct(d):
    d = str(d).replace("-", "")
    if d in breadth_by_date:
        a, b = breadth_by_date[d]
        if b >= 10:
            return a / b * 100
    return None


md.append("\n### B1. 入场日广度桶 × 结果")
md.append("| 广度 % (上证20MA上方股票比例) | n | v22 avg | v22 PF | v24 avg | v24 PF |")
md.append("|---|---|---|---|---|---|")
by_br = defaultdict(list)
for r in rows:
    b = breadth_pct(r["entry_date"])
    if b is None:
        continue
    if b < 30:
        bk = "<30% (极弱)"
    elif b < 50:
        bk = "30-50% (弱)"
    elif b < 70:
        bk = "50-70% (中)"
    else:
        bk = "≥70% (强)"
    by_br[bk].append(r)
for b in ("<30% (极弱)", "30-50% (弱)", "50-70% (中)", "≥70% (强)"):
    rs = by_br.get(b, [])
    if rs:
        n0, a0, _, p0 = st(rs)
        _, a1, _, p1 = st(rs, "_w")
        md.append(f"| {b} | {n0} | {a0} | {p0} | {a1} | {p1} |")

# ─── A2. S15 反事实: 熊市加速段(15-30bar) ×1.25 加权 ───
md.append("\n## D. S15 反事实: 熊市加速段(bear_streak 15-30) 入场 ×1.25")
tot = pos = neg = 0.0
ws = 0.0
for r in rows:
    m = 1.25 if (15 <= r["_bs"] < 30) else 1.0
    w2 = float(r.get("_w") or 1) * m if "last" in r else float(r.get("v23_weight") or 1) * m
    p = float(r["net_pnl_pct"] or 0)
    tot += p * w2
    ws += w2
    if p > 0:
        pos += p * w2
    else:
        neg += -p * w2
md.append(f"| v24 | avg | PF |")
md.append(f"|---|---|---|")
md.append(f"| 当前 S1-S14 | 5.89 | 5.89 |")
md.append(f"| 加 S15(熊加速段×1.25) | {tot / ws:.2f} | {pos / neg:.2f} |")

# ─── C. R86 ─ 生产新单影子审计 ───
md.append("\n## C. R86: 生产挂单影子标签审计")
led = json.load(open(os.path.join(ROOT, "paper_ledger.json"), encoding="utf-8"))
orders = led if isinstance(led, list) else led.get("orders", [])
with_v23 = [o for o in orders if isinstance(o, dict) and o.get("v23")]
md.append(f"带 v23 标的订单: **{len(with_v23)}/{len(orders)}** (2026-09-21 起才有标签)")
md.append("\n| code | 信号日 | 状态 | weight | flags |")
md.append("|---|---|---|---|---|")
for o in sorted(with_v23, key=lambda x: -int(str(x.get("signal_date") or "").replace("-", ""))):
    md.append(f"| {o.get('code')} | {o.get('signal_date')} | {o.get('status')} | {o['v23'].get('weight')} | {'<br>'.join(o['v23'].get('flags') or [])[:80]} |")

with_jev = [o for o in orders if isinstance(o, dict) and o.get("jev")]
md.append(f"\n带 Jev 判定的订单: {len(with_jev)}")
md.append("| code | kind | conf |")
md.append("|---|---|---|")
for o in with_jev[-10:]:
    j = o["jev"]
    md.append(f"| {o.get('code')} | {j.get('event_kind', '-')} | {j.get('event_conf', '-')} |")

open(OUT, "w", encoding="utf-8").write("\n".join(md))
print(f"R85/86 → {OUT}")
