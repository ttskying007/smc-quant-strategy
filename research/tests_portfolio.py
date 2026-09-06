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

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
