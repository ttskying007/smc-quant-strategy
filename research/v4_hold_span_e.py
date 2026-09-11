# -*- coding: utf-8 -*-
"""v4_hold_span_e.py —— 事件腿持有期 × E 环境交互审计(预注册 #39)
背景: v0 事件腿的 hold_bars 有长尾(勤上股份 TP4_RUNNER 21%), 退出规则是 TP 阶梯。
预注册:
  H1 v0 台账 pnl 按信号日 E 分档(锁定切点): 若 E 档单调 → 事件腿也吃 E(环境因子跨腿普适)
  H2 若事件腿不单调(与结构腿 mid 峰不同构) → 事件腿 E 使用方式应为"排序"而非"分档"(如实报)
  H3 hold_bars × E 交互: 弱市(E低)持有期应变短(TP 难达成) —— 若反, 是阶梯管理的滞后成本"""
import json, sys, io, statistics
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

E = {d["d8"]: d.get("e") for d in json.load(open(
    r"E:\test\smc_project\research\handover\escore_history_full.json", encoding="utf-8")
).get("days", []) if d.get("e") is not None}

v0 = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
closed = [t for t in v0 if t.get("status") == "CLOSED" and t.get("pnl_pct") is not None]
print(f"CLOSED: {len(closed)}")

def band(e):
    return None if e is None else ("low" if e <= 0.4559 else "mid" if e <= 0.5562 else "high")

stats = defaultdict(list)
hold = defaultdict(list)
for t in closed:
    d8 = str(t.get("signal_date") or "").replace("-", "")
    bd = band(E.get(d8))
    if bd is None:
        continue
    stats[bd].append(t["pnl_pct"])
    if t.get("hold_bars"):
        hold[bd].append(t["hold_bars"])

print("\nH1 事件腿 pnl × E 档:")
avgs = {}
for bd in ("low", "mid", "high"):
    v = stats.get(bd, [])
    if v:
        avgs[bd] = round(sum(v) / len(v), 2)
        print(f"  {bd}: n={len(v)} avg={avgs[bd]} wr={round(len([x for x in v if x>0])/len(v)*100,1)}%")
    else:
        print(f"  {bd}: n=0")
mono = avgs.get("low", 0) < avgs.get("mid", 0) < avgs.get("high", 0) if len(avgs) == 3 else False
print(f"H1 单调(low<mid<high): {mono}")

print("\nH3 hold_bars × E 档:")
for bd in ("low", "mid", "high"):
    v = hold.get(bd, [])
    if v:
        print(f"  {bd}: n={len(v)} avg_hold={round(statistics.mean(v),1)}")
    else:
        print(f"  {bd}: n=0 (无hold_bars记录)")

# H3 交互方向: 弱市持有应短
holds = {bd: round(statistics.mean(v), 1) for bd, v in hold.items() if v}
h3 = holds.get("low", 99) <= holds.get("high", 0) if len(holds) >= 2 else None
verdict = {
    "H1_事件腿E档单调": mono,
    "H1_avgs": avgs,
    "H2_事件腿E使用应为排序(非单调如实报)": not mono,
    "H3_弱市持有更短": h3,
    "hold_avgs": holds,
}
print("\n预注册:", json.dumps(verdict, ensure_ascii=False))
json.dump(verdict, open(r"E:\test\smc_project\research\handover\V4_事件腿E交互.json", "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_事件腿E交互.json")