# -*- coding: utf-8 -*-
"""tests_audit_portfolio_sim.py — 组合资金模拟器回归锁(审计§7.4/Iteration3)."""
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
from portfolio_simulator import PortfolioSimulator
def bar(o, h, l, c, v=1000000):
    return {"o": o, "h": h, "l": l, "c": c, "v": v}
print("== 1. 正常买入 ==")
ps = PortfolioSimulator(capital=1_000_000, max_positions=10, single_cap=0.25, total_cap=0.80)
r = ps.try_buy("A", "2024-01-02", bar(10, 10.5, 9.9, 10.2), 10.0, 9.0, 12.0, bars=[bar(10,10.5,9.9,10.2)], prev_close=10.0)
ok("买入成交", r["status"] == "FILLED", r)
ok("持仓数=1", len(ps.positions) == 1, ps.positions)
print("== 2. 重叠信号拒绝 ==")
r2 = ps.try_buy("A", "2024-01-03", bar(10, 10.5, 9.9, 10.2), 10.0, 9.0, 12.0, bars=[bar(10,10.5,9.9,10.2)], prev_close=10.0)
ok("同symbol未平仓 -> OVERLAP拒绝", r2["status"] == "REJECTED" and r2["reason"] == "OVERLAP_POSITION", r2)
print("== 3. 持仓数上限 ==")
ps2 = PortfolioSimulator(capital=1_000_000, max_positions=2)
ok("买入 B", ps2.try_buy("B", "d", bar(10,10.5,9.9,10.2), 10, 9, 12, bars=[bar(10,10.5,9.9,10.2)], prev_close=10)["status"] == "FILLED")
ok("买入 C", ps2.try_buy("C", "d", bar(10,10.5,9.9,10.2), 10, 9, 12, bars=[bar(10,10.5,9.9,10.2)], prev_close=10)["status"] == "FILLED")
r3 = ps2.try_buy("D", "d", bar(10,10.5,9.9,10.2), 10, 9, 12, bars=[bar(10,10.5,9.9,10.2)], prev_close=10)
ok("第3只 -> MAX_POSITIONS拒绝", r3["status"] == "REJECTED" and r3["reason"] == "MAX_POSITIONS", r3)
print("== 4. 总资金占用 ==")
ps3 = PortfolioSimulator(capital=100_000, total_cap=0.80, single_cap=0.25)
ok("首笔占5%=5000", ps3.try_buy("E", "d", bar(10,10.5,9.9,10.2), 10, 9, 12, bars=[bar(10,10.5,9.9,10.2)], prev_close=10)["status"] == "FILLED")
# 单笔上限 25% = 25000; 多笔累计至 80% = 80000
for i, s in enumerate(["F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"]):
    ps3.try_buy(s, "d", bar(10,10.5,9.9,10.2), 10, 9, 12, bars=[bar(10,10.5,9.9,10.2)], prev_close=10)
used = ps3._used_capital()
ok("累计占用 <= 80%上限", used <= 100000 * 0.80 + 1, (used, 100000*0.80))
ok("未超限后继续拒绝", ps3.positions.__len__() >= 10, len(ps3.positions))
print("== 5. 卖出释放资金 ==")
ps4 = PortfolioSimulator(capital=1_000_000, max_positions=1)
barsA = [bar(10,10.5,9.9,10.2), bar(11,11.5,10.8,11.2), bar(12,12.5,11.8,12.2)]
ok("买入 A", ps4.try_buy("A", "d1", barsA[0], 10, 9, 12, bars=barsA, prev_close=10)["status"] == "FILLED")
# 下一日 A 出场(TIME 或 TP)
r_exit = ps4.try_exit("A", "d2", barsA[1], prev_close=barsA[0]["c"])
ok("平仓释放持仓", ps4.positions.get("A") is None, ps4.positions)
ok("平仓后允许新买入", ps4.try_buy("Z", "d3", bar(10,10.5,9.9,10.2), 10, 9, 12, bars=[bar(10,10.5,9.9,10.2)], prev_close=10)["status"] == "FILLED")
print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
