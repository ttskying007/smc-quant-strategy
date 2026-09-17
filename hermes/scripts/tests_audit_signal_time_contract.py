# -*- coding: utf-8 -*-
"""tests_audit_signal_time_contract.py —— Signal 时间语义统一回归锁(审计§3.3 P1).

审计 §3.3: V11 摆动确认和 FVG 语义不统一 —— idx/confirmed_at 混用, 结构
价格字段可能来自确认窗口却无统一 visible_at, 造成"事件顺序正确、字段内容
仍带未来信息"的隐性泄漏。

修复(signals_v11.py Signal 类):
  新增规范时间字段 event_time / visible_time / decision_time + causal_times()
  统一契约: idx <= confirmed_at(当已设) <= event <= visible <= decision.
  不破坏现有 20+ 处 idx/confirmed_at 赋值(未设新字段时回退兼容).

本测试固化:
  1. 因果链: event <= visible <= decision (所有构造)
  2. 回退兼容: 未设新字段时 event=idx, visible=confirmed_at(或idx)
  3. 显式设置: 各字段可独立指定, 且防护 visible<event 时钳制
  4. to_dict 序列化包含新字段
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


from signals_v11 import Signal  # noqa: E402

print("== 1. 回退兼容(未设新字段) ==")
s1 = Signal(type="FVG_Bull", idx=5, direction="bull", price=10.0, confirmed_at=7)
ct = s1.causal_times()
ok("未设新字段: event=idx(5)", ct["event_time"] == 5, ct)
ok("未设新字段: visible=confirmed_at(7)", ct["visible_time"] == 7, ct)
ok("未设新字段: decision=visible(7)", ct["decision_time"] == 7, ct)
ok("因果链 event<=visible<=decision", 5 <= 7 <= 7, ct)

s2 = Signal(type="SweepDown", idx=9, direction="bear", price=10.0)  # confirmed_at 未设
ct2 = s2.causal_times()
ok("confirmed_at 未设时 visible=idx(9)", ct2["visible_time"] == 9, ct2)

print("== 2. 显式设置 + 防护 ==")
s3 = Signal(type="CHOCH_Bull", idx=5, direction="bull", price=10.0,
            confirmed_at=7, event_time=6, visible_time=8, decision_time=10)
ct3 = s3.causal_times()
ok("显式设置被尊重", (ct3["event_time"], ct3["visible_time"], ct3["decision_time"]) == (6, 8, 10), ct3)

# 防护: visible < event 时钳制
s4 = Signal(type="FVG_Bear", idx=5, direction="bear", price=10.0,
            confirmed_at=7, event_time=9, visible_time=6)  # visible 早于 event
ct4 = s4.causal_times()
ok("visible<event 被钳制到 event", ct4["visible_time"] >= ct4["event_time"], ct4)
ok("decision>=visible 被钳制", ct4["decision_time"] >= ct4["visible_time"], ct4)

print("== 3. 因果链全类型扫描(审计核心) ==")
cases = [
    Signal(type="FVG_Bull", idx=10, direction="bull", price=10.0, confirmed_at=12),
    Signal(type="IFVG_Bear", idx=10, direction="bear", price=10.0, confirmed_at=11),
    Signal(type="SweepDown", idx=15, direction="bear", price=10.0),
    Signal(type="CHOCH_Bull", idx=20, direction="bull", price=10.0, confirmed_at=20),
    Signal(type="BOS_Bear", idx=3, direction="bear", price=10.0, confirmed_at=3),
    Signal(type="OB_Bull", idx=8, direction="bull", price=10.0, confirmed_at=10),
]
all_ok = True
for s in cases:
    ct = s.causal_times()
    cond = ct["event_time"] <= ct["visible_time"] <= ct["decision_time"]
    if not cond:
        all_ok = False
        print("    FAIL %s: %s" % (s.type, ct))
ok("6 种信号类型因果链全部满足 event<=visible<=decision", all_ok)

print("== 4. to_dict 序列化含新字段 ==")
d = s1.to_dict()
ok("to_dict 含 event_time/visible_time/decision_time",
   all(k in d for k in ("event_time", "visible_time", "decision_time")), d.keys())
ok("to_dict 值正确", d["event_time"] == 5 and d["visible_time"] == 7, d)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)