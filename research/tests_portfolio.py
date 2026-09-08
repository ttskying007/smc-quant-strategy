# -*- coding: utf-8 -*-
"""core/portfolio.py 单元测试（审计 G24）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import portfolio as PF

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 风险仓位 ==")
sz = PF.position_size(100000, 0.01, entry=10.0, stop=9.0)
ok("10万×1%风险/(10-9)=1000股", abs(sz - 1000) < 1e-6, str(sz))
ok("无效参数→0", PF.position_size(100000, 0.01) == 0)

print("== 开仓节流 ==")
ok_ok, why = PF.throttle_open([True]*10, {"A": 2}, max_positions=10)
ok("达最大持仓→拒绝", not ok_ok and why == "MAX_POSITIONS")
ok_ok2, why2 = PF.throttle_open([True], {"A": 3}, max_positions=10, max_sector=3)
ok("同板块3只→拒绝", not ok_ok2 and why2 == "MAX_SECTOR")
ok_ok3, why3 = PF.throttle_open([True]*5, {}, max_positions=10, max_daily_opens=5)
ok("单日新开5→拒绝", not ok_ok3 and why3 == "MAX_DAILY_OPEN")
ok("正常→OK", PF.throttle_open([True], {"A": 1}, max_positions=10)[0])

print("== 权益/回撤 ==")
eq = PF.equity_curve([+10, -50, +20])
ok("净值复利", abs(eq[-1] - (1.1*0.5*1.2)) < 1e-9, str(eq[-1]))
mdd, _, _ = PF.max_drawdown([1.0, 1.1, 0.55, 0.66])
ok("MDD=50%", abs(mdd - 0.5) < 1e-6, str(mdd))

print("== HHI 集中度 ==")
ok("均匀→HHI小", PF.hhi([10, 10, 10, 10]) < 0.3, str(PF.hhi([10,10,10,10])))
ok("单月集中→HHI高", PF.hhi([90, 1, 1, 1]) > 0.6, str(PF.hhi([90,1,1,1])))

vals, h = PF.monthly_contribution([1,2,3,4,5], ["01","01","02","02","03"])
ok("月度聚合", vals == [3.0, 7.0, 5.0], str(vals))

print("== P1-5 组合级风险 ==")
# 总暴露
ok_e, why_e, tot = PF.portfolio_exposure_check([{"code": "a", "position_pct": 0.22}, {"code": "b", "position_pct": 0.22}], max_total_exposure=0.4)
ok("总暴露0.44>0.4→拒绝", not ok_e and "总暴露" in why_e, why_e)
ok_e2, _, tot2 = PF.portfolio_exposure_check([{"code": "a", "position_pct": 0.2}], max_total_exposure=0.8)
ok("总暴露0.2<0.8→OK", ok_e2, str(tot2))
ok_b, why_b, _ = PF.portfolio_exposure_check([{"code": "a", "position_pct": 0.3}], max_single=0.25)
ok("单票0.3>0.25→拒绝", not ok_b and "单票" in why_b, why_b)
# 行业集中
ok_i, why_i, byind = PF.industry_concentration_check(
    [{"code": "a", "position_pct": 0.3}, {"code": "b", "position_pct": 0.2}],
    {"a": "BANK", "b": "BANK"}, max_industry=0.4)
ok("行业BANK 0.5>0.4→拒绝", not ok_i and "BANK" in why_i, why_i)
ok_i2, _, _ = PF.industry_concentration_check(
    [{"code": "a", "position_pct": 0.2}, {"code": "b", "position_pct": 0.2}],
    {"a": "BANK", "b": "TECH"}, max_industry=0.4)
ok("两行业各0.2→OK", ok_i2)
# kill switch
k1, why1, _ = PF.kill_switch([-0.01]*5, window="consecutive", consecutive_loss=5)
ok("连续5亏→kill", k1, why1)
k2, _, _ = PF.kill_switch([-0.01, +0.02, -0.01, +0.03, -0.01], window="consecutive", consecutive_loss=5)
ok("非连续5亏→不kill", not k2)
k3, why3, _ = PF.kill_switch([-0.02]*20, window="daily", daily_loss=-0.03)
ok("近20笔-40%→daily kill", k3, why3)
# 订单幂等
d, r = PF.idempotent_order_check(
    [{"code": "600000", "signal_date": "20260907", "order_type": "MARKET_T1_OPEN"}],
    {"code": "600000", "signal_date": "20260907", "order_type": "MARKET_T1_OPEN"})
ok("同code+日期+类型→重复", d, r)
d2, _ = PF.idempotent_order_check(
    [{"code": "600000", "signal_date": "20260907", "order_type": "MARKET_T1_OPEN"}],
    {"code": "600000", "signal_date": "20260908", "order_type": "MARKET_T1_OPEN"})
ok("不同日期→非重复", not d2)
# 跳空风险
gl, br = PF.gap_risk_check({"position_pct": 0.2, "sl": 9.0}, gap_pct=-0.08)
ok("8%跳空×20%仓=1.6%账户损失", abs(gl - 0.016) < 1e-9, str(gl))
ok("缺口<仓位50%→非breach", not br)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
