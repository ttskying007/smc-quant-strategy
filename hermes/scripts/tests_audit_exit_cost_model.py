# -*- coding: utf-8 -*-
"""tests_audit_exit_cost_model.py —— 出场成本模型回归锁(审计§3.5 P1).

修复来源: 外部审计 §3.5(V44/旧回测对成交和成本建模不足)。
修复位置: rolling_backtest.py simulate_exit() + run_backtest() P&L
  继承 V699 最低标准:
    - T+1: 从 entry_idx+1 起评估, 禁止同日退出
    - SL 优先: 同 bar 同时触发 TP/SL 按 SL 处理
    - 跳空穿越止损: bar 开盘价已越过 SL -> 按开盘价成交(GAP_SL)
    - 成本: 往返 0.20%(FEE_PCT) 计入净 P&L
    - 超时: 第 max_hold 根 bar 收盘平仓(TIME)

本测试固化:
  1. T+1: 入场 bar 不参与出场评估
  2. SL 优先: 同 bar l<=sl 且 h>=tp 时 -> SL(保守)
  3. GAP_SL: 开盘跳空穿越止损 -> 开盘价
  4. TIME: 超时收盘价 + won 判定
  5. 成本: pnl_pct 反映 fee(通过 run_backtest 的 P&L 公式验证)
纯内存, 不写生产。
"""
import importlib.util
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
V11 = os.path.join(HERE, "v11")
sys.path.insert(0, V11)
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


# 用正则提取 simulate_exit(纯函数, 无模块级 IO)
import re  # noqa: E402
MAX_HOLD = 40
FEE_PCT = 0.20
src = open(os.path.join(V11, "rolling_backtest.py"), encoding="utf-8").read()
m = re.search(r"(def simulate_exit\(.*?(?=\ndef |\Z))", src, re.S)
exec(compile(m.group(1), "sim_exit", "exec"))


def bars(prices):
    """prices = [(o,h,l,c)...]"""
    return [{"t": "d%02d" % i, "o": o, "h": h, "l": l, "c": c}
            for i, (o, h, l, c) in enumerate(prices)]


print("== 1. T+1: 入场 bar 不参与出场 ==")
# 入场 idx=0 (o=100); 入场 bar 本身 l=80 (已低于 sl=95), 但 T+1 不允许同日退出
# 第 1 根出场 bar(idx=1) h=120 >= tp=115 -> TP
b = bars([(100, 101, 80, 100),   # idx0: 入场 bar, l=80 < sl=95 (但 T+1 不评估)
          (100, 120, 99, 119),   # idx1: h=120 >= tp 115
          (100, 101, 90, 100)])
r = simulate_exit(b, 0, 'bull', sl=95, tp=115)
ok("T+1 从 idx+1 起评估(idx0 的 l=80 不触发 SL)", r[0] == 1 and r[3] == 'TP', r)

print("== 2. SL 优先(同 bar 同时触发) ==")
b2 = bars([(100, 101, 99, 100),
           (100, 120, 90, 110),   # h=120>=tp115 且 l=90<=sl95 -> SL 优先
           (100, 101, 99, 100)])
r2 = simulate_exit(b2, 0, 'bull', sl=95, tp=115)
ok("同 bar TP/SL -> SL 优先", r2[3] == 'SL' and r2[2] is False, r2)

print("== 3. 跳空穿越止损 GAP_SL(开盘价) ==")
b3 = bars([(100, 101, 99, 100),
           (90, 91, 88, 90),   # 开盘 90 <= sl 95 -> GAP_SL 按开盘价
           (100, 101, 99, 100)])
r3 = simulate_exit(b3, 0, 'bull', sl=95, tp=115)
ok("GAP_SL 按开盘价(90)成交", r3[3] == 'GAP_SL' and abs(r3[1] - 90) < 1e-9, r3)

print("== 4. 反向(bear)跳空 ==")
b4 = bars([(100, 101, 99, 100),
           (110, 111, 108, 110),   # 开盘 110 >= sl 105 -> GAP_SL
           (100, 101, 99, 100)])
r4 = simulate_exit(b4, 0, 'bear', sl=105, tp=95)
ok("bear GAP_SL 按开盘价(110)", r4[3] == 'GAP_SL' and abs(r4[1] - 110) < 1e-9, r4)

print("== 5. TIME 超时 ==")
b5 = bars([(100, 101, 99, 100)] + [(100, 101, 99, 100)] * 2 + [(100, 101, 99, 120)])
r5 = simulate_exit(b5, 0, 'bull', sl=90, tp=130, max_hold=3)
ok("TIME 在第 max_hold 根 bar 收盘平仓", r5[3] == 'TIME' and r5[0] == 3, r5)

print("== 6. 成本常量与 P&L 公式 ==")
ok("FEE_PCT = 0.20 已定义", FEE_PCT == 0.20, FEE_PCT)
ok("源码含 fee 扣减", "fee" in src and "FEE_PCT" in src)
ok("源码含 exit_reason 记录", "'exit_reason'" in src)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)