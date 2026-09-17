# -*- coding: utf-8 -*-
"""tests_audit_multi_tf.py — 多周期职责分离回归锁(审计§6.1/§6.2/Iteration 5)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V25 = os.path.join(HERE, "v25")
V11 = os.path.join(HERE, "v11")
sys.path.insert(0, V25)
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


import multi_tf  # noqa: E402

# 提取 v44_engine.synthesize_weekly(仅函数体, 不 import 模块避免 IO)
src = open(os.path.join(V11, "v44_engine.py"), encoding="utf-8").read()
start = src.find("def synthesize_weekly")
end = src.find("\ndef ", start + 10)
func_src = src[start:end] if end > start else src[start:]
import datetime as _dt
ns = {"datetime": _dt.datetime}
exec(compile(func_src, "v44sw", "exec"), ns)
v44_synthesize_weekly = ns["synthesize_weekly"]

print("== 1. 多周期职责合同 ==")
c = multi_tf.role_contract()
ok("周线=仅已完成周期方向", c["weekly"] == "MARKET_DIRECTION_ONLY_COMPLETED_BARS", c)
ok("日线=核心结构", c["daily"] == "CORE_STRUCTURE_SIGNAL", c)
ok("15m=仅执行质量", c["m15"] == "EXECUTION_QUALITY_ONLY", c)

print("== 2. completed_weekly_only 丢弃未完成周 ==")
import datetime as dt  # noqa: E402
bars = []
px = 10.0
for wk in range(3):
    for d in range(5):
        t = dt.date(2024, 1, 1) + dt.timedelta(days=wk * 7 + d)
        bars.append({"date": t.isoformat(), "o": px, "h": px * 1.01,
                     "l": px * 0.99, "c": px * 1.002, "v": 1000})
        px *= 1.01
for d in range(3):
    t = dt.date(2024, 1, 22) + dt.timedelta(days=d)
    bars.append({"date": t.isoformat(), "o": px, "h": px * 1.01,
                 "l": px * 0.99, "c": px * 1.002, "v": 1000})
    px *= 1.01
# V44 fallback(date[:6]) 在同月内恒定会死循环(审计§6.2 点名的缺陷) ->
# 测试数据加 week 字段(V44 首选键), 用 ISO 周编号使每周独立成组
import calendar as _cal
for b in bars:
    d0 = dt.date.fromisoformat(b["date"])
    b["week"] = d0.isocalendar()[1]
w = multi_tf.completed_weekly_only(bars)
ok("3完整周+3半周 -> 3根(半周丢弃)", len(w) == 3, len(w))

print("== 3. V44 synthesize_weekly 修复后丢弃未完成周 ==")
w44 = v44_synthesize_weekly(bars)
ok("V44 修复后 3完整周+3半周 -> 3根", len(w44) == 3, len(w44))

print("== 3b. V44 无 week 字段时 ISO fallback 正确分组(§6.2) ==")
# 去掉 week 字段, 验证 fallback(ISO 周编号)不再整月并成一组
bars_no_week = []
for b in bars:
    b2 = dict(b)
    b2.pop("week", None)
    bars_no_week.append(b2)
w44b = v44_synthesize_weekly(bars_no_week)
ok("V44 无week字段 ISO fallback -> 3根(半周丢弃)", len(w44b) == 3, len(w44b))

print("== 4. 15m 执行质量 ==")
r = multi_tf.exec_quality_ok({"o": 11.0, "v": 1000}, 10.0, "bull")
ok("涨停拒执行", r["ok"] is False and r["reason"] == "LIMIT_UP", r)
r2 = multi_tf.exec_quality_ok({"o": 10.0, "v": 0}, 10.0, "bull")
ok("无流动性拒执行", r2["ok"] is False, r2)
r3 = multi_tf.exec_quality_ok({"o": 10.0, "v": 1000}, 10.0, "bull")
ok("正常可执行", r3["ok"] is True, r3)

print("== 5. 日线信号就绪(无未来) ==")
d = multi_tf.daily_signal_ready({"date": "2024-01-05"}, True, True)
ok("确认摆动+OB就绪 -> ready", d["ready"] is True, d)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)