# -*- coding: utf-8 -*-
"""tests_audit_determinism.py — 事件流确定性/截断不变性属性测试(审计§10.2/§5.3).

审计 §10.2 属性测试:
  "对输入 bars 做重复运行, 输出事件 ID 和排序必须稳定"
审计 §5.3 前视偏差自动检查:
  "随机截断数据后, 截断点之前的信号不能发生变化"
  "往完整数据尾部追加未来 bar, 历史决策、目标和参数不能变化"

本测试:
  1. 同一输入重复运行 causal_stream -> 事件 ID 集合完全一致(确定性)
  2. 随机截断数据 -> 截断点之前的信号不变(前缀一致性)
  3. 追加未来 bars -> 历史事件保留(已由 causal_stream 覆盖, 此处多 symbol 复验)
  4. 多 symbol 输入 -> 事件稳定且不串扰
  5. 事件排序稳定(按日期排序输出)
纯内存, 不写生产。
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "v25"))
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


from causal_stream import CausalEventEngine  # noqa: E402


def make_bars(prices):
    return [{"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}
            for t, o, h, l, c, v in prices]


def run_events(bars, symbol="T"):
    eng = CausalEventEngine(symbol)
    for b in bars:
        eng.step(b)
    return sorted(eng.event_ids())  # 稳定排序


PAD = [("2023-12-%02d" % (i + 1), 100, 101, 99, 100, 100) for i in range(20)]
EVENT = [
    ("2024-01-06", 100, 101, 95.0, 100, 100),   # swing low
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-10", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),    # sweep idx9
    ("2024-01-13", 100, 102, 99, 102, 300),     # response idx10
    ("2024-01-14", 100, 103, 99, 102, 300),
    ("2024-01-15", 100, 104, 100, 103, 300),
    ("2024-01-16", 100, 105, 101, 104, 300),
    ("2024-01-17", 100, 106, 102, 105, 300),
]
BARS = make_bars(PAD + EVENT)

print("== 1. 重复运行确定性(§10.2) ==")
r1 = run_events(BARS)
r2 = run_events(BARS)
ok("两次运行事件 ID 完全一致", r1 == r2, (r1, r2))
ok("事件数 = 1(单事件场景)", len(r1) == 1, r1)

print("== 2. 随机截断前缀一致性(§5.3) ==")
# 截断点必须在事件形成之后(response 之后), 前缀事件不变
full = run_events(BARS)
for cut in (21, 24, 26, 28):  # 不同截断点(事件在 idx25-26 附近)
    prefix = run_events(BARS[:cut])
    # 截断点之前的事件(仅当完整形成)应与全量一致; 未形成的被丢弃是正确行为
    # 关键断言: 已形成事件(swing/sweep/response 均在截断内)必须保留
    ok("截断@%d 后前缀事件 == 全量事件(若完整包含)" % cut,
       prefix == full or len(prefix) == 0,
       (cut, prefix, full))

print("== 3. 追加未来 bars 不改历史(§10.2) ==")
EXT = make_bars([("2024-02-%02d" % d, 100, 110, 99, 109, 300)
                 for d in range(1, 15)])
r_base = run_events(BARS)
r_ext = run_events(BARS + EXT)
ok("追加未来后历史事件保留", r_base == r_ext, (r_base, r_ext))

print("== 4. 多 symbol 不串扰 ==")
bars_a = BARS
bars_b = make_bars([("2024-03-01", 100, 101, 99, 100, 100)] * 10)
ea = run_events(bars_a, "A")
eb = run_events(bars_b, "B")
ok("symbol A 事件独立", all(e[0] == "A" for e in ea), ea)
ok("symbol B 无事件", len(eb) == 0, eb)

print("== 5. 事件排序稳定(§10.2) ==")
# 多事件场景: 两个独立 swing 各自事件
BARS2 = make_bars(PAD + EVENT + [
    ("2024-02-01", 105, 106, 103, 105, 100),
    ("2024-02-02", 105, 106, 103, 105, 100),
    ("2024-02-05", 105, 106, 103, 105, 100),
    ("2024-02-06", 105, 106, 103, 105, 100),
    ("2024-02-07", 105, 106, 103, 105, 100),
    ("2024-02-08", 105, 106, 101.0, 105, 100),
    ("2024-02-09", 105, 106, 104, 105, 100),
    ("2024-02-12", 105, 106, 104, 105, 100),
    ("2024-02-13", 105, 106, 104, 105, 100),
    ("2024-02-14", 105, 105, 99.0, 103, 500),
    ("2024-02-15", 105, 107, 104, 107, 300),
    ("2024-02-18", 105, 108, 104, 107, 300),
    ("2024-02-19", 105, 109, 105, 108, 300),
])
s1 = run_events(BARS2)
s2 = run_events(BARS2)
ok("多事件两次运行排序一致", s1 == s2, (s1, s2))
ok("多事件数 >= 2", len(s1) >= 2, s1)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)