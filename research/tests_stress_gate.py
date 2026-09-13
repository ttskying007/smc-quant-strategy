# -*- coding: utf-8 -*-
"""tests_stress_gate.py —— R10: 预注册压力门纯函数锁(2026-09-13)。
四段: recompute_net 成本重算 / stress_costs G1 / subwindow_stability G2 / concentration G3。
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reject_stress_gate as G
import paper_sim

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

FEE = paper_sim.CFG.FEE_PCT

print("== 1. recompute_net 成本重算 ==")
t = {"net_pnl_pct": 2.0, "filled": True}  # gross = 2.0 + 0.20 = 2.20
ok("基线倍数还原", G.recompute_net(t, FEE) == 2.0, G.recompute_net(t, FEE))
ok("费率×2: 2.20−0.40=1.80", G.recompute_net(t, FEE * 2) == 1.8)
# 滑点×2: slip_extra=0.001 → 额外 0.2%
ok("费率×2+滑点×2: −0.4−0.2", G.recompute_net(t, FEE * 2, 0.001) == 1.6)
ok("净值为负的单", G.recompute_net({"net_pnl_pct": -1.0, "filled": True}, FEE) == -1.0)

print("== 2. stress_costs G1 ==")
def mktrades(nets):
    return [{"net_pnl_pct": x, "filled": True} for x in nets]
r = G.stress_costs(mktrades([2.0, -1.0, 3.0, 0.5, 1.0]))
ok("G1 正样本 avg>0 PF>1 → pass", r["pass"] is True, r)
r2 = G.stress_costs(mktrades([-2.0, -1.0, 0.5]))  # avg<0
ok("G1 avg<0 → fail", r2["pass"] is False, r2)
r3 = G.stress_costs([])  # 空
ok("G1 空 → not pass", r3["pass"] is False and r3["avg_net"] is None, r3)
r4 = G.stress_costs(mktrades([5.0, 5.0, 5.0]))  # 无亏损
ok("G1 无亏损样本 PF=None 但 pass(全胜)", r4["pf"] is None and r4["pass"] is True, r4)

print("== 3. subwindow_stability G2 ==")
def mkt(nets):
    return [{"net_pnl_pct": x, "filled": True, "date": f"202606{i+1:02d}"} for i, x in enumerate(nets)]
s = G.subwindow_stability(mkt([1] * 6), n_sub=3)
ok("G2 全正 3/3 → pass", s["pass"] is True and s["pos_windows"] == 3, s)
s2 = G.subwindow_stability(mkt([1, 1, 1, -1, -1, 5]), n_sub=3)
ok("G2 混合窗 2/3 → pass", s2["pass"] is True, s2)
s3 = G.subwindow_stability(mkt([-1] * 6), n_sub=3)
ok("G2 全负 → fail", s3["pass"] is False, s3)
s4 = G.subwindow_stability(mkt([1, 2]), n_sub=3)
ok("G2 样本不足 → fail+why", s4["pass"] is False and "不足" in s4["why"], s4)

print("== 4. concentration G3 ==")
c = G.concentration(mktrades([1.0] * 30))  # n=30 去top3 后仍 avg 1.0
ok("G3 均匀样本去top后仍正 → pass", c["pass"] is True and abs(c["avg_after_trim"] - 1.0) < 1e-9, c)
c2 = G.concentration(mktrades([-0.1] * 29 + [50.0]))  # 全靠1笔
ok("G3 全靠单笔 → trim后负 fail", c2["pass"] is False and c2["avg_full"] > 0, c2)
c3 = G.concentration(mktrades([1.0] * 10))
ok("G3 n<20 → None 不适用", c3["pass"] is None and "不适用" in c3["why"], c3)
c4 = G.concentration(mktrades([-1.0] * 30))
ok("G3 全负 full<0 → fail", c4["pass"] is False and c4["avg_full"] < 0, c4)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)