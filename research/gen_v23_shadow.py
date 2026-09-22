# -*- coding: utf-8 -*-
"""gen_v23_shadow.py — R70: v23 影子组合(预注册, 不改生产)
规则(全部 as-weight, 即只降权不删除, 记录全貌):
  s1_choch  : breakout_kind 含 CHoCH    → weight ×0.5      (病灶 P1)
  s4_rank2  : rank == 2                 → weight ×0.5      (病灶 P4)
  s5_r5min  : risk_pct < 5%             → weight ×0.6      (病灶 P5)
基线 = v22 冻结 1858 腿; v23 = 同腿 × 权重; 统计对比即可。
纪律: 不修改 v22 任何文件; v23 仅生成 combo_v23_shadow.csv + 统计。
"""
import csv, os
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "combo_v22_trades.csv")
OUT = os.path.join(ROOT, "combo_v23_shadow.csv")

W_CHOCH = 0.5
W_RANK2 = 0.5
W_RISK_LT5 = 0.6


def st(rows, wkey=None):
    n = len(rows)
    tw = sum(r[wkey] for r in rows) if wkey else n
    if not n or tw == 0:
        return n, round(tw, 1), 0, 0, 0
    if wkey:
        p = [float(r["net_pnl_pct"] or 0) * r[wkey] for r in rows]
    else:
        p = [float(r["net_pnl_pct"] or 0) for r in rows]
    avg = sum(p) / tw
    wr = sum(r[wkey] if wkey else 1 for r, v in zip(rows, p) if v > 0) / tw * 100
    pos = sum(v for v in p if v > 0)
    neg = -sum(v for v in p if v < 0)
    return n, round(tw, 1), round(avg, 2), round(wr, 1), round(pos / neg, 2) if neg else 999


rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
for r in rows:
    w = 1.0
    flags = []
    if "CHoCH" in (r.get("breakout_kind") or ""):
        w *= W_CHOCH; flags.append("s1_choch")
    if str(r.get("rank")) == "2":
        w *= W_RANK2; flags.append("s4_rank2")
    try:
        if float(r.get("risk_pct") or 0) < 5:
            w *= W_RISK_LT5; flags.append("s5_risk_lt5")
    except Exception:
        pass
    r["v23_weight"] = round(w, 3)
    r["v23_flags"] = "|".join(flags) or "none"

cols = list(rows[0].keys())
with open(OUT, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

print(f"v23 影子 legs: {len(rows)}")
print(f"含规则标记者: {sum(1 for r in rows if r['v23_flags'] != 'none')} 腿({sum(1 for r in rows if r['v23_flags'] != 'none')/len(rows)*100:.0f}%)")
print()
print("| 版本 | n | Σw | avg% | WR% | PF |")
print("|---|---|---|---|---|---|")
print("| v22 基线 |", " | ".join(str(x) for x in st(rows)), "|")
print("| v23 影子(加权) |", " | ".join(str(x) for x in st(rows, "v23_weight")), "|")
print()
print("逐年:")
by_y = defaultdict(list)
for r in rows:
    by_y[r["entry_date"][:4]].append(r)
print("| 年 | v22 avg/PF | v23 avg/PF |")
print("|---|---|---|")
for y in sorted(by_y):
    b = st(by_y[y]); v = st(by_y[y], "v23_weight")
    print(f"| {y} | {b[2]}%/PF {b[4]} | {v[2]}%/PF {v[4]} |")
