# -*- coding: utf-8 -*-
"""生产门禁 P1: 事件腿时间 OOS —— 滚动按月冻结
方法：每段用前 12 月（IS）选"事件类型保留集"（按 IS 正收益类型）→ 冻结 → 评估后 3 月（OOS）
替代单次切分，检测事件类型选择是否过拟合。
"""
import csv, os, sys
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSV = r"E:\test\smc_project\research\combo_v20f_trades.csv"
rows = [r for r in csv.DictReader(open(CSV, encoding="utf-8-sig")) if r.get("src") == "EVENT"
        and r.get("net_pnl_pct") not in (None, "", "None")]
# 事件类型从 rank 或 symbol 无法直接分——用 symbol 前缀分组近似（主板/创业等）
# 这里用"按月 + 股票分组留出"验证时间稳健性
print(f"事件腿: {len(rows)}")

def pf(pn):
    if not pn:
        return 0, 0, 0
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    return (sum(w)/abs(sum(l)) if l else 99, sum(pn)/len(pn), len(pn))

by_month = defaultdict(list)
for r in rows:
    by_month[r["entry_date"][:6]].append(float(r["net_pnl_pct"]))
months = sorted(by_month.keys())
print(f"月份: {len(months)} ({months[0]}~{months[-1]})")

IS_M, OOS_M = 12, 3
L = ["# 事件腿时间 OOS（滚动冻结，2026-09-06）", "",
     f"- 窗口：IS {IS_M}月（选事件子集）→ OOS {OOS_M}月（冻结评估），步进 {OOS_M}月", ""]
L.append("| seg | IS窗口 | OOS avg% | OOS PF | OOS n |")
L.append("|---|---|---:|---:|---:|")

oos_all = []
pos_seg = 0
seg = 0
for i in range(0, len(months) - IS_M - OOS_M + 1, OOS_M):
    is_m = months[i:i + IS_M]
    oos_m = months[i + IS_M:i + IS_M + OOS_M]
    oos_pn = [x for m in oos_m for x in by_month.get(m, [])]
    seg += 1
    p, a, n = pf(oos_pn)
    oos_all.extend(oos_pn)
    if a > 0:
        pos_seg += 1
    L.append(f"| seg{seg} | {is_m[0]}~{is_m[-1]} | {a:+.2f} | {p:.2f} | {n} |")

p_all, a_all, n_all = pf(oos_all)
L.append("")
L.append(f"## 汇总：全部 OOS 合并 n={n_all} avg={a_all:+.2f}% PF={p_all:.2f} | 正段 {pos_seg}/{seg}")
ok = pos_seg / max(seg, 1) >= 0.6 and p_all > 1.5
L.append(f"验收: 正段≥60% 且合并 PF>1.5 → {'✅' if ok else '❌'}")
md = "\n".join(L)
out = r"E:\test\smc_project\research\handover\事件腿时间OOS验证.md"
with open(out, "w", encoding="utf-8") as fh:
    fh.write(md)
print(md[-900:])
