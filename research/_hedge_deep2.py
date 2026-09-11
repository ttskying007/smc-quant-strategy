# -*- coding: utf-8 -*-
"""_hedge_deep2.py —— 两个深回撤段定位 + E 环境对照(滚动回撤的时间结构)"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\shadow_ledger.json", encoding="utf-8"))
tr = sorted(led["trades"], key=lambda t: t["entry_date"])

# 定位: 逐笔累计(单位: pct 累加), 找回撤 < −40pt 的起止
eq = pk = 0.0
dd = 0.0
seg = []
start_i = 0
for i, t in enumerate(tr):
    eq += t["net_pnl_pct"]
    pk = max(pk, eq)
    cur = eq - pk
    if cur < -40 and not seg:
        seg.append((i, tr[i]["entry_date"]))
    if seg and cur >= -40:
        pass
# 更直接: 打印 #150-200 和 #330-360 对应的日期
for lo, hi in ((150, 200), (330, 360)):
    print(f"#{lo}-{hi}: 日期 {tr[lo]['entry_date']} ~ {tr[hi]['entry_date']}")
    pnls = [t["net_pnl_pct"] for t in tr[lo:hi + 1]]
    neg = [x for x in pnls if x < 0]
    print(f"  n={len(pnls)} avg={round(sum(pnls)/len(pnls),2)} 负笔率={round(len(neg)/len(pnls)*100)}% "
          f"负笔均值={round(sum(neg)/max(1,len(neg)),2)} 最差5笔={sorted(pnls)[:5]}")
# E 环境对照(E 历史在 2023-06 后才有, 检查这两个时段有没有 E 记录)
E = {}
try:
    h = json.load(open(r"E:\test\smc_project\research\handover\escore_history_full.json", encoding="utf-8"))
    E = {d["d8"]: d.get("e") for d in h.get("days", []) if d.get("e") is not None}
except Exception:
    pass
import statistics
for lo, hi in ((150, 200), (330, 360)):
    es = [E.get(t["entry_date"]) for t in tr[lo:hi + 1]]
    es = [x for x in es if x is not None]
    if es:
        print(f"  时段 E: n={len(es)} 均值={round(statistics.mean(es),3)} min={min(es)} max={max(es)}")
    else:
        print(f"  时段 E: 无记录(早于 E 历史)")
# 2026 年退化确认: 半年切
y26 = [t for t in tr if t["entry_date"] >= "20260101"]
h1 = [t["net_pnl_pct"] for t in y26 if t["entry_date"] < "20260701"]
h2 = [t["net_pnl_pct"] for t in y26 if t["entry_date"] >= "20260701"]
for lbl, v in (("2026H1", h1), ("2026H2", h2)):
    if v:
        print(f"{lbl}: n={len(v)} avg={round(sum(v)/len(v),2)} wr={round(len([x for x in v if x>0])/len(v)*100,1)}%")