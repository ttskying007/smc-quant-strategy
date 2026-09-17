# -*- coding: utf-8 -*-
"""tests_audit_replay_chain.py — 端到端经济回放链回归锁(审计§5.1/§5.3/Iteration 3)."""
import os
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


from replay_chain import ReplayChain, DecisionPolicy  # noqa: E402
from causal_stream import CausalEventEngine  # noqa: E402


def make_bars(prices):
    return [{"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}
            for t, o, h, l, c, v in prices]


# 事件场景: swing(idx5) -> sweep(idx9) -> response(idx10) -> entry(idx11)
PAD = [("2023-12-%02d" % (i + 1), 100, 101, 99, 100, 100) for i in range(20)]
EVENT = [
    ("2024-01-06", 100, 101, 95.0, 100, 100),   # swing low
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-10", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),    # sweep idx9
    ("2024-01-13", 100, 102, 99, 102, 300),     # response idx10
    ("2024-01-14", 100, 103, 99, 102, 300),     # entry idx11 (T+1 open)
    ("2024-01-15", 100, 104, 100, 103, 300),
    ("2024-01-16", 100, 105, 101, 104, 300),
    ("2024-01-17", 100, 106, 102, 105, 300),
    ("2024-01-18", 100, 107, 103, 106, 300),
]
BARS = make_bars(PAD + EVENT)

print("== 1. 事件流识别(§5.3 在线一致) ==")
eng = CausalEventEngine("T")
for b in BARS:
    eng.step(b)
ev = eng.event_ids()
ok("识别 1 个事件", len(ev) == 1, ev)

print("== 2. 决策生成候选(仅入场前可见) ==")
pol = DecisionPolicy()
cands = pol.decide(ev, {"T": BARS}, {})
ok("生成 1 个候选", len(cands) == 1, cands)
if cands:
    c = cands[0]
    ok("入场=次日开盘价", abs(c["entry_price"] - 100) < 1e-9, c["entry_price"])
    ok("sl < entry(止损在下方)", c["sl"] < c["entry_price"], c)
    ok("tp > entry(目标在上方)", c["tp"] > c["entry_price"], c)

print("== 3. 端到端回放链 ==")
chain = ReplayChain(capital=1_000_000, max_positions=10)
res = chain.run({"T": BARS})
ok("台账含 1 笔交易", len(res["trades"]) == 1, res["trades"])
ok("合同 hash 生成", len(res["contract_hash"]) == 16, res["contract_hash"])
ok("生产写入=False", chain.contract["production_write"] is False, chain.contract)

print("== 4. 无事件场景 -> 无交易 ==")
FLAT = make_bars(PAD + [("2024-01-06", 100, 101, 99, 100, 100)] * 8)
chain2 = ReplayChain()
res2 = chain2.run({"T": FLAT})
ok("无事件 -> 0 交易 0 候选", len(res2["trades"]) == 0 and res2["n_events"] == 0, res2)

print("== 5. 追加未来 bar 不改变历史(§10.2) ==")
chain3 = ReplayChain()
res3 = chain3.run({"T": BARS})
# 追加更多未来 bars
EXT = make_bars([("2024-02-%02d" % d, 100, 110, 99, 109, 300) for d in range(1, 8)])
chain4 = ReplayChain()
res4 = chain4.run({"T": BARS + EXT})
ok("追加未来后历史交易数不变", len(res3["trades"]) == len(res4["trades"]),
   (len(res3["trades"]), len(res4["trades"])))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)