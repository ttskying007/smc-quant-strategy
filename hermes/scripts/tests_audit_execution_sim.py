# -*- coding: utf-8 -*-
"""tests_audit_execution_sim.py — 严格成交模拟器回归锁(审计§7.4/Iteration 3)."""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
V25 = os.path.join(HERE, "v25")
sys.path.insert(0, V25)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))
from execution_simulator import (execute_open, simulate_exit_strict,
                                 is_limit_move, is_suspended, capacity_check,
                                 portfolio_guard, FEE_PCT)
def bar(o, h, l, c, v=1000):
    return {"o": o, "h": h, "l": l, "c": c, "v": v}
print("== 1. 涨跌停拒交 ==")
ok("涨停拒买", is_limit_move(bar(11.0, 11.1, 10.9, 11.0), 10.0, "buy"))
ok("跌停拒卖", is_limit_move(bar(9.0, 9.1, 8.9, 9.0), 10.0, "sell"))
r = execute_open(bar(11.0, 11.1, 10.9, 11.0, 1000), 10.0, "bull")
ok("execute_open 涨停 -> REJECTED", r["status"] == "REJECTED" and r["reason"] == "LIMIT_UP", r)
print("== 2. 停牌拒绝 ==")
ok("停牌(开盘0)拒交", is_suspended(bar(0, 0, 0, 0)))
ok("停牌(无量)拒交", is_suspended(bar(10, 10.1, 9.9, 10.0, 0)))
r2 = execute_open(bar(0, 0, 0, 0), 10.0, "bull")
ok("execute_open 停牌 -> REJECTED", r2["status"] == "REJECTED" and r2["reason"] == "SUSPENDED", r2)
print("== 3. 成交量容量 ==")
c1 = capacity_check(bar(10, 10.1, 9.9, 10.0, 100), 0.05, 1_000_000)
ok("容量不足 -> REJECTED", c1[0] is False and c1[1] == "CAPACITY_EXCEEDED", c1)
c2 = capacity_check(bar(10, 10.1, 9.9, 10.0, 10000000), 0.05, 1_000_000)
ok("容量充足 -> OK", c2[0] is True, c2)
print("== 4. 出场约束 ==")
# T+1 + SL 优先 + 跳空
bars = [bar(100, 101, 99, 100), bar(100, 120, 90, 110), bar(100, 101, 99, 100)]
r3 = simulate_exit_strict(bars, 0, 100.0, "bull", sl=95, tp=115)
ok("同bar TP/SL -> SL优先", r3["reason"] == "SL", r3)
bars2 = [bar(100, 101, 99, 100), bar(90.5, 91, 88, 90.5), bar(100, 101, 99, 100)]
r4 = simulate_exit_strict(bars2, 0, 100.0, "bull", sl=95, tp=115)
ok("跳空穿越 -> GAP_SL按开盘价", r4["reason"] == "GAP_SL" and abs(r4["exit_price"] - 90.5) < 1e-9, r4)
print("== 5. 跌停持仓延续 ==")
# 跌停日(卖不出) -> 跳过, 之后正常平仓
bars3 = [bar(100, 101, 99, 100),
         bar(90.0, 90.5, 89.5, 90.0),     # 跌停日: o=90 <= 100*0.9 -> 跌停,跳过(持仓延续)
         bar(90.5, 91.5, 89.8, 91.0),     # 次日 o=90.5 > 90*0.9=81 非跌停; o=90.5 <= sl=94 -> GAP_SL
         bar(95, 96, 94, 95)]
# prev_close 依次为 100 -> 100(跌停跳过) -> 90(跳过) -> 95
r5 = simulate_exit_strict(bars3, 0, 100.0, "bull", sl=94, tp=120, prev_close=100)
ok("跌停日(bar1)被跳过,次日(bar2)触发GAP_SL", r5["exit_idx"] == 2 and r5["reason"] == "GAP_SL" and abs(r5["exit_price"] - 90.5) < 1e-9, r5)
print("== 6. 成本扣除 ==")
ok("net = gross - 0.20%", abs(r5["net_pnl_pct"] - r5["gross_pnl_pct"] + FEE_PCT) < 1e-9, r5)
print("== 7. 组合资金 ==")
ok("超持仓数 -> 拒绝", portfolio_guard(10, 0.5)[0] is False)
ok("总仓位超限 -> 拒绝", portfolio_guard(3, 0.79)[0] is False)
ok("正常 -> 通过", portfolio_guard(3, 0.3)[0] is True)
print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
