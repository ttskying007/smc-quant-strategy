# -*- coding: utf-8 -*-
"""v4_cross_day_span.py —— 跨日持仓重叠审计(预注册 #38)
背景: PAPER 结构腿持仓 15bar + 事件腿挂单等待 → 系统是否会出现同股双腿重叠
      (同一股既有事件腿持仓又有结构腿挂单)? max_daily_open=5 的容量语义是否被跨腿穿透?
预注册:
  X1 PAPER setup 台账(21 信号) vs v0 事件腿台账(139): 同股交集非空 → 跨腿重叠存在
  X2 若交集非空: 重叠期内两腿独立挂单 → 实际敞口=2×设计 → 容量控制失真
  X3 若交集空: 两腿候选池天然分离(事件腿要求 ACCUM/DOWNTREND 阶段,
     结构腿要求 UPTREND/MARKUP —— 阶段互斥设计自带的分离)"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 两腿符号集
paper = json.load(open(r"E:\test\smc_project\research\handover\setup_engine_paper_ledger.json", encoding="utf-8"))
p_syms = {s["code"] for s in paper.get("signals", [])}
v0 = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
v0_syms = {str(t["code"]).split(".")[0] for t in v0}
print(f"PAPER 结构腿: {len(p_syms)} 股; v0 事件腿: {len(v0_syms)} 股")
inter = p_syms & v0_syms
print(f"X1 同股交集: {len(inter)} 股 {sorted(inter) if inter else '(空)'}")

# X2 深挖: 若有交集, 看日期是否重叠(事件腿持仓窗 15bar vs 结构腿挂单窗 5bar)
if inter:
    p_dates = {s["code"]: s["date"] for s in paper["signals"]}
    v0_dates = {}
    for t in v0:
        c = str(t["code"]).split(".")[0]
        if c in inter:
            v0_dates.setdefault(c, []).append((t.get("signal_date"), t.get("status")))
    print("\nX2 重叠明细:")
    for c in sorted(inter):
        print(f"  {c}: 结构腿信号 {p_dates.get(c)} | 事件腿 {v0_dates.get(c)}")
else:
    print("X3: 阶段互斥设计(ACCUM/DOWNTREND vs UPTREND/MARKUP)自带分离 ✓")

# 补充: 两腿阶段要求的机制性分离验证(统计 v0 台账 stage 字段)
stages = {}
for t in v0:
    st = t.get("stage")
    if st:
        stages[st] = stages.get(st, 0) + 1
print(f"\nv0 事件腿 stage 分布: {stages}")
verdict = {
    "X1_交集非空": bool(inter),
    "X2_重叠期敞口失真": bool(inter),   # 待日期核对细化
    "X3_阶段互斥分离": not inter,
    "交集": sorted(inter),
    "v0_stage分布": stages,
}
json.dump(verdict, open(r"E:\test\smc_project\research\handover\V4_跨腿重叠审计.json", "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n预注册:", json.dumps({k: v for k, v in verdict.items() if k != "v0_stage分布"}, ensure_ascii=False))
print("已写 handover/V4_跨腿重叠审计.json")