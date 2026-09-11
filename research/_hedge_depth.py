# -*- coding: utf-8 -*-
"""_hedge_depth.py —— SHADOW 风险指标扩展: 分年度表现 + 滚动 MDD + 蒙特卡洛破产概率
(上轮普查确认 500 笔干净 → 本轮从"干净"进到"风险刻画")"""
import json, random, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = json.load(open(r"E:\test\smc_project\research\shadow_ledger.json", encoding="utf-8"))
tr = sorted(led["trades"], key=lambda t: t["entry_date"])
pnls = [t["net_pnl_pct"] for t in tr]

# ① 分年度
by_year = defaultdict(list)
for t in tr:
    by_year[str(t["entry_date"])[:4]].append(t["net_pnl_pct"])
print("分年度:")
for y in sorted(by_year):
    v = by_year[y]
    w = sum(x for x in v if x > 0); l_ = abs(sum(x for x in v if x <= 0))
    print(f"  {y}: n={len(v)} avg={round(sum(v)/len(v),2)} wr={round(len([x for x in v if x>0])/len(v)*100,1)}% pf={round(w/l_,2) if l_ else 99}")

# ② 滚动 50 笔窗口 avg/MDD(每 10 笔采样)
print("滚动 50 笔(每 10 采样):")
worst = []
for i in range(0, len(pnls) - 50, 10):
    win = pnls[i:i + 50]
    eq, pk, mdd = 0, 0, 0
    for x in win:
        eq += x
        pk = max(pk, eq)
        mdd = min(mdd, eq - pk)
    worst.append((round(mdd, 1), round(sum(win) / 50, 2)))
    print(f"  #{i}: avg={round(sum(win)/50,2)} mdd={round(mdd,1)}")
print(f"最差滚动窗: mdd={min(worst)[0]} avg={min(worst,key=lambda x:x[0])[1]}")

# ③ 蒙特卡洛破产(40% 回撤线): 固定 50% 仓位近似, 费后
random.seed(20260913)
N_SIM = 5000
ruin = 0
max_dd_dist = []
for _ in range(N_SIM):
    eq, pk, mdd = 1.0, 1.0, 0.0
    # 抽 500 笔(有放回), 仓位 50%
    for _ in range(500):
        r = random.choice(pnls) / 100 * 0.5
        eq *= (1 + r)
        pk = max(pk, eq)
        mdd = min(mdd, eq / pk - 1)
        if eq < 0.6:
            ruin += 1
            break
    max_dd_dist.append(mdd)
max_dd_dist.sort()
print(f"蒙特卡洛({N_SIM}次×500笔×50%仓位): 破产(eq<0.6)={ruin}/{N_SIM}={ruin/N_SIM*100:.2f}%")
print(f"  MDD 中位={max_dd_dist[N_SIM//2]*100:.1f}% 95分位={max_dd_dist[int(N_SIM*0.95)]*-1*100:.1f}% 最差={max_dd_dist[-1]*100:.1f}%")