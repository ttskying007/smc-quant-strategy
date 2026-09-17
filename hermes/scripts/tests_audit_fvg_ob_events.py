# -*- coding: utf-8 -*-
"""tests_audit_fvg_ob_events.py — FVG/OB 事件回归锁(审计§4.2/§4.3)."""
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


from fvg_ob_events import (detect_fvgs, FvgTracker, detect_obs, ObTracker)  # noqa: E402


def bars_from(prices):
    return [{"date": t, "o": o, "h": h, "l": l, "c": c, "v": v}
            for t, o, h, l, c, v in prices]


def with_pad(events, pad_n=15):
    """前加 pad_n 根温和波动 bar(建立形成前 ATR≈2, 使小 gap 可达标)."""
    pad = [("p%02d" % i, 100, 101, 99, 100, 1000) for i in range(pad_n)]
    return bars_from(pad + events)


print("== 1. FVG 检测: 三根 bar 可见(§4.2) ==")
B1 = with_pad([
    ("d0", 100, 100, 99, 99, 1000),
    ("d1", 99, 99, 98, 98, 1000),
    ("d2", 101, 103, 101, 103, 1000),   # b3.l=101 > b1.h=100 -> bullish FVG
    ("d3", 103, 104, 102, 103, 1000),
    ("d4", 103, 104, 102, 103, 1000),
])
ev = detect_fvgs(B1)
bull = [e for e in ev if e["direction"] == "bull"]
ok("检测到 bullish FVG", len(bull) >= 1, ev)
if bull:
    e = bull[0]
    ok("visible_at = formed_at + 2", e["visible_at"] == e["formed_at"] + 2, e)
    ok("价格区间正确(lower=100, upper=101)", e["lower"] == 100 and e["upper"] == 101, e)
    ok("state=ACTIVE(初始)", e["state"] == "ACTIVE", e)

print("== 2. FVG 状态机: MITIGATED/INVALIDATED(§4.2) ==")
tracker = FvgTracker(ev)
for _i in range(len(B1)):
    tracker.step(B1[_i], _i)
# B1 无填充(低点102 > 100) -> 应保持 ACTIVE
st_all = tracker.states()
b_states = [v for k, v in st_all.items() if "BULL" in k]
ok("未填补保持 ACTIVE", b_states and all(v == "ACTIVE" for v in b_states), st_all)

# 构造填充场景: 低点 <= 100
B1b = with_pad([
    ("d0", 100, 100, 99, 99, 1000),
    ("d1", 99, 99, 98, 98, 1000),
    ("d2", 101, 103, 101, 103, 1000),
    ("d3", 103, 104, 99, 100, 1000),   # 低点99 <= 100 -> 完全填补
])
evb = detect_fvgs(B1b)
tb = FvgTracker(evb)
for _i in range(len(B1b)):
    tb.step(B1b[_i], _i)
sb = tb.states()
bullb = [v for k, v in sb.items() if "BULL" in k]
ok("完全填补 -> MITIGATED", bullb and bullb[0] == "MITIGATED", sb)

print("== 3. FVG 最小宽度(形成前 ATR, 无未来) ==")
B2 = with_pad([
    ("d0", 100, 100.05, 99.95, 100, 1000),
    ("d1", 100, 100.05, 99.95, 100, 1000),
    ("d2", 100, 100.08, 100.02, 100, 1000),  # gap 极小
])
ok("极小 gap 不产生 FVG(宽度归一化)", len(detect_fvgs(B2)) == 0, detect_fvgs(B2))

print("== 4. OB 检测: BOS 证据(§4.3) ==")
B3 = bars_from([
    ("d0", 100, 101, 99, 100, 1000),
    ("d1", 100, 101, 99, 100, 1000),
    ("d2", 100, 101, 99, 100, 1000),
    ("d3", 100, 101, 99, 100, 1000),
    ("d4", 100, 101, 99, 100, 1000),
    ("d5", 102, 108, 101, 107, 3000),   # 实体5% > 2%, 收盘107 > 前高101 -> BOS
])
obs = detect_obs(B3)
bullob = [o for o in obs if o["direction"] == "bull"]
ok("检测到 bullish OB(含 BOS 证据)", len(bullob) >= 1, obs)
if bullob:
    o = bullob[0]
    ok("BOS 证据: 突破前高 101", o["bos_evidence"]["break_above"] == 101, o["bos_evidence"])
    ok("区域 = [open, high]", o["region"] == (102, 108), o["region"])
    ok("state=ACTIVE, tests=0", o["state"] == "ACTIVE" and o["tests"] == 0, o)

print("== 5. OB 状态机: 回测/失效穿越计数(§4.3) ==")
ot = ObTracker(obs)
B4 = bars_from([
    ("d6", 103, 104, 101, 103, 1000),   # 低点101 <= 108 -> 回测
    ("d7", 101, 102, 100, 101, 1000),   # 低点100 < 下沿102? 收盘101 < 102 -> 失效
])
for _i, _b in enumerate(B4):
    ot.step(_b, 6 + _i)
st = ot.states()
so = [v for k, v in st.items() if "BULL" in k]
ok("回测计数 >= 1", so and so[0]["tests"] >= 1, st)

print("== 6. 无未来(visible_at 不早于形成) ==")
for e in detect_fvgs(B1):
    ok("FVG visible_at >= formed_at+2", e["visible_at"] >= e["formed_at"] + 2, e)
for o in detect_obs(B3):
    ok("OB visible_at == formed_at", o["visible_at"] == o["formed_at"], o)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)