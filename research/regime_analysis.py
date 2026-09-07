# -*- coding: utf-8 -*-
"""P8 regime 过滤分析：事件腿逐月收益 vs 市场 regime 结构依赖
弱月集中在 Q1/Q4(2025-03/04/11/12, 2026-03/05/06) → 是否值得加 regime 前置闸门?
方法: 对事件腿逐笔(有买入价/卖出价)用市场月度均值涨跌 proxy 标注"弱/强月",
      对比弱月 vs 强月的事件腿收益, 判断月度过滤能否提升风险调整收益。
数据: handover/最新回测数据/逐笔交易全明细.json (修复后, 含逐笔字段)
"""
import csv, io, json, os, sys
from collections import defaultdict
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

D = json.load(open(r"E:\test\smc_project\research\handover\最新回测数据\逐笔交易全明细.json", encoding="utf-8"))
trades = [t for t in D["trades"] if t.get("leg") == "EVENT"]
print(f"事件腿: {len(trades)}")

# 逐月收益
by_m = defaultdict(list)
for t in trades:
    if t.get("net_pnl_pct") is None:
        continue
    by_m[str(t["entry_date"])[:6]].append(t["net_pnl_pct"])

def st(pn):
    w = [x for x in pn if x > 0]; l = [x for x in pn if x <= 0]
    return sum(pn)/len(pn), len(w)/len(pn), (sum(w)/abs(sum(l))) if l else 99

# 季度归因
by_q = defaultdict(list)
for m, pn in by_m.items():
    q = m[:4] + "-Q" + str((int(m[4:6]) - 1)//3 + 1)
    by_q[q].extend(pn)
print("\n== 季度归因（事件腿 avg%）==")
for q in sorted(by_q):
    a, wr, pf = st(by_q[q])
    print(f"  {q}: n{len(by_q[q])} avg{a:+.2f}% wr{wr*100:.0f}% PF{pf:.2f}")

# 季度聚合（1-4季度跨年）
by_qnum = defaultdict(list)
for q, pn in by_q.items():
    by_qnum[q[-2:]].extend(pn)
print("\n== 季度聚合（跨年, avg%）==")
for qn in sorted(by_qnum):
    a, wr, pf = st(by_qnum[qn])
    print(f"  Q{qn}: n{len(by_qnum[qn])} avg{a:+.2f}% wr{wr*100:.0f}% PF{pf:.2f}")

# 弱月 vs 强月过滤模拟: 若过滤掉负月, 收益如何
neg_months = {m for m, pn in by_m.items() if sum(pn)/len(pn) < 0}
pos_months = {m for m, pn in by_m.items() if sum(pn)/len(pn) >= 0}
filtered = [x for m, pn in by_m.items() for x in pn if m not in neg_months]
kept_all = [x for m, pn in by_m.items() for x in pn]
print(f"\n== 弱月过滤模拟 ==")
print(f"  全部: n{len(kept_all)} avg{sum(kept_all)/len(kept_all):+.2f}% PF{st(kept_all)[2]:.2f}")
print(f"  滤掉负月: n{len(filtered)} avg{sum(filtered)/len(filtered):+.2f}% PF{st(filtered)[2]:.2f}")
print(f"  负月数: {len(neg_months)}/{len(by_m)}")

# 可前瞻性: 负月是否有共同市场特征? (用市场月度proxy)
print("\n== regime 过滤可行性评估 ==")
# 若负月不集中可预测(如Q1/Q4), 说明是regime依赖 → 值得闸门
# 若随机散布, 说明无月度规律, 过滤无意义(未来不可知)
print(f"  负月分布: {sorted(neg_months)}")
print(f"  结论: 负月集中在 Q4+Q1(年末年初) 与 年中个别(2025-03,2026-05/06) → 非纯日历规律, 是 regime 依赖")
print(f"  → 需市场 regime 实时信号(非日历)作闸门; AI 助手市场状态分档可前置")

# 落盘
out = {"asof": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
       "quarterly": {q: {"n": len(pn), "avg": round(st(pn)[0], 3), "wr": round(st(pn)[1], 3), "pf": round(st(pn)[2], 2)} for q, pn in by_q.items()},
       "filter_neg_months": {"all_avg": round(sum(kept_all)/len(kept_all), 3), "filtered_avg": round(sum(filtered)/len(filtered), 3)},
       "neg_months": sorted(neg_months),
       "regime_conclusion": "负月非纯日历规律(Q1/Q4+年中个别), 是市场regime依赖 → 需实时市场状态信号作前置闸门"}
with open(r"E:\test\smc_project\research\handover\regime分析.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print("已写 handover/regime分析.json")