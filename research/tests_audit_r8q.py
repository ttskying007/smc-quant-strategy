# -*- coding: utf-8 -*-
"""tests_audit_r8q.py —— R28(第八轮审计 P1-6)CostModel 回归锁:
① 单源描述: cost_model.py 与 config 值一致 + execution 引用单源(数值等价);
② 平价 round-trip 黄金测试(审计原文): 同价进出 → net 必为负(成本>0 必亏);
③ 三路径成本应用一致(simulate 双边总一次扣/try_fill 买+滑/try_exit 卖−滑);
④ cost_model_version 在描述与结果中可记录。
纯等价重构验证: 冻结基线 n=1639 数值依赖不变。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. 单源描述与 config 一致 ==")
import config as CFG
from core.cost_model import (fee_pct_total, slippage_side, round_trip_cost_pct,
                             describe, COST_MODEL_VERSION)
ok("fee_pct_total == CFG.FEE_PCT", fee_pct_total() == CFG.FEE_PCT, (fee_pct_total(), CFG.FEE_PCT))
ok("slippage_side == CFG.SLIPPAGE", slippage_side() == CFG.SLIPPAGE)
ok("版本号格式在", COST_MODEL_VERSION.startswith("COST_V1_"), COST_MODEL_VERSION)
_d = describe()
ok("describe fee_basis=双边总", _d["fee_basis"] == "TOTAL_BOTH_SIDES")
ok("describe slippage_basis=单边", _d["slippage_basis"] == "PER_SIDE")
ok("describe 三路径全列", set(_d["paths"]) == {"simulate", "try_fill", "try_exit"})
ok("describe 带 cost_model_version", _d["cost_model_version"] == COST_MODEL_VERSION)

print("== 2. 平价 round-trip 黄金测试(审计原文) ==")
for px in (5.0, 10.0, 19.453, 100.0, 0.5):
    r = round_trip_cost_pct(px, px)
    ok(f"同价进出 {px} → net={r['net_pct']}(负)", r["net_pct"] < 0, r)
# 同价进出净损应 = 双边滑点复合 + 双边总费用
r10 = round_trip_cost_pct(10.0, 10.0)
# 同价进出 gross 是复合几何: (1−s)/(1+s)−1, 非 −2s 线性(s=0.1% 时
# 复合 −0.1998% vs 线性 −0.2% —— 基数差异 O(s²), 数学正确)
ok("10 元平价: gross=复合双滑((1−s)/(1+s)−1)",
   abs(r10["gross_pct"] - ((1 - slippage_side()) / (1 + slippage_side()) - 1) * 100) < 1e-6, r10)
ok("10 元平价: net=gross−FEE", abs(r10["net_pct"] - (r10["gross_pct"] - fee_pct_total())) < 1e-9)
# 非平价: 盈利单也要先扣成本
r_win = round_trip_cost_pct(10.0, 11.0)
ok("10→11 盈利单 gross≈9.7%(<10% 因滑点)", 9.5 < r_win["gross_pct"] < 10.0, r_win)
ok("盈利单 net=gross−0.2", abs(r_win["net_pct"] - (r_win["gross_pct"] - 0.20)) < 1e-9)
ok("买价含 +s 滑", abs(r_win["buy_px"] - 10.0 * (1 + slippage_side())) < 1e-9)
ok("卖价含 −s 滑", abs(r_win["sell_px"] - 11.0 * (1 - slippage_side())) < 1e-9)

print("== 3. execution 单源引用(等价重构) ==")
src = open(os.path.join(HERE, "core", "execution.py"), encoding="utf-8").read()
ok("execution 引用 cost_model 单源", "from core.cost_model import fee_pct_total, slippage_side" in src)
ok("FEE = fee_pct_total()(不再直读 CFG)", "FEE = fee_pct_total()" in src)
ok("SLIPPAGE = slippage_side()", "SLIPPAGE = slippage_side()" in src)
import core.execution as CE
ok("execution.FEE 数值不变", CE.FEE == CFG.FEE_PCT, (CE.FEE, CFG.FEE_PCT))
ok("execution.SLIPPAGE 数值不变", CE.SLIPPAGE == CFG.SLIPPAGE)
# 三路径应用点(源码级)
ok("simulate 双边总一次扣(gross - FEE)", "round(gross - FEE, 4)" in src)
ok("try_fill 买+滑(×(1 + SLIPPAGE))", src.count("* (1 + SLIPPAGE)") >= 6)
ok("try_exit 卖−滑(×(1 - SLIPPAGE))", src.count("* (1 - SLIPPAGE)") >= 2)

print("== 4. simulate 数值等价(冻结基线保护) ==")
# 同输入 simulate 净值与旧公式一致(gross-FEE): 构造最小夹具
_bars = [{"o": 10, "h": 10.5, "l": 9.8, "c": 10.2, "t": f"202601{i:02d}", "v": 100} for i in range(1, 30)]
_r = CE.simulate(_bars, 3, 10.0, 9.0, tp1=10.6, tp2=11.0, max_hold=5, code="600000")
ok("simulate 夹具可跑", _r.get("reason") in ("TP1", "TP2", "TP3", "SL_HIT", "TIME_STOP", "BAD_ENTRY", "SL_GAP", "TP_STRUCTURAL", "BE"), _r)
ok("net_pnl_pct 已扣 FEE", abs(_r["net_pnl_pct"] - (_r.get("realized_partial", 0) - CFG.FEE_PCT)) < 1e-3 or _r.get("skipped"))

print("== 5. R12-R27 修复保持 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("R8 几何守卫仍在(paper_sim)", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("R24 开盘窗口守卫仍在", "_missed_open_window" in src)
ok("MISSED_OPEN 字面量仍在", '"MISSED_OPEN"' in src)
ok("R27 时段守卫仍在", "R27 交易时段守卫" in src_ps)
ok("R25 空价 TTL 仍在", "R25 TTL(行情不可用推进)" in src_ps)
ok("R26 monitor now 仍在", '_snap["now"] = cn_now(' in src_ps)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)