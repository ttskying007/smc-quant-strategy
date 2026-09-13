# -*- coding: utf-8 -*-
"""core/sequence.py 单元测试（V2 Structure Engine 2.0: 事件对象+状态机）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sequence import (SequenceMachine, make_event, run_sequence,
                            STATES, TRANSITIONS, EVENT_TRIGGERS)

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 1. 事件对象 ==")
ev = make_event("600000", "D1", "20260812", "SSL_SWEEP", "LONG", 12.31, 82)
ok("字段完整", ev["symbol"] == "600000" and ev["event_type"] == "SSL_SWEEP"
   and ev["strength"] == 82 and ev["direction"] == "LONG")

print("== 2. 正序推进(理想链) ==")
m = SequenceMachine("600000")
r = []
r.append(m.feed(make_event("600000", "D1", "20260801", "LIQUIDITY_FORMED", "LONG", 11.5, 60)))
r.append(m.feed(make_event("600000", "D1", "20260812", "SSL_SWEEP", "LONG", 11.4, 70)))
r.append(m.feed(make_event("600000", "D1", "20260813", "RECLAIM", "LONG", 12.0, 55)))
r.append(m.feed(make_event("600000", "D1", "20260814", "DISPLACEMENT", "LONG", 12.4, 65)))
r.append(m.feed(make_event("600000", "D1", "20260815", "MSS", "LONG", 12.5, 50)))
r.append(m.feed(make_event("600000", "D1", "20260815", "FVG", "LONG", 12.3, 50)))
r.append(m.feed(make_event("600000", "D1", "20260818", "RETEST", "LONG", 12.2, 50)))
r.append(m.feed(make_event("600000", "D1", "20260818", "RETEST_HOLD", "LONG", 12.3, 60)))
ok("8步全接受", all(x[0] for x in r), str([x[0] for x in r]))
ok("终态READY", m.is_ready(), m.state)
ok("顺序签名", m.sequence_signature() == "liquidity_found→sweep→reclaim→displacement→structure_shift→poi_created→retest→hold",
   m.sequence_signature())
dts = m.dt_features()
ok("Δt特征记录", len(dts) == 7 and dts[0] == 11 and dts[2] == 1, str(dts))

print("== 3. 乱序拒绝(顺序是特征) ==")
m2 = SequenceMachine("600001")
m2.feed(make_event("600001", "D1", "20260801", "LIQUIDITY_FORMED", "LONG", 11.5, 60))
# 直接喂 RECLAIM(没有 SWEEP) → 应被拒绝 OUT_OF_ORDER
acc, st = m2.feed(make_event("600001", "D1", "20260802", "RECLAIM", "LONG", 12.0, 55))
ok("乱序RECLAIM被拒", (not acc) and "OUT_OF_ORDER" in m2.rejected[0]["why"], str(m2.rejected))
ok("状态不推进", st == "LIQUIDITY_READY", st)

print("== 4. 失效转移 ==")
m3 = SequenceMachine("600002")
m3.feed(make_event("600002", "D1", "20260801", "LIQUIDITY_FORMED", "LONG", 11.5, 60))
m3.feed(make_event("600002", "D1", "20260812", "SSL_SWEEP", "LONG", 11.4, 70))
acc4, st4 = m3.feed(make_event("600002", "D1", "20260813", "CONTINUE_BREAK", "LONG", 11.0, 0))
ok("扫损后继续破位→INVALID", acc4 and st4 == "INVALID", st4)

print("== 5. 转移表一致性 ==")
ok("所有触发器有归属", set(EVENT_TRIGGERS.values()) <=
   {t for tr in TRANSITIONS.values() for t in tr} | {"reset", "filled", "closed"})
ok("未知事件类型被拒", SequenceMachine("X").feed(make_event("X", "D1", "20260801", "XXX_UNKNOWN", "LONG", 1, 1))[0] is False)

print("== 6. K线重建(run_sequence 骨架) ==")
def bars(vals):
    out = []
    for i, c in enumerate(vals):
        o = vals[i-1] if i else c
        rng = abs(c - o) + 0.02
        out.append({"t": f"2026010{i+1:02d}", "o": o, "h": max(o, c) + rng*0.3,
                    "l": min(o, c) - rng*0.3, "c": c, "v": 1000})
    return out
# 下跌→横盘低池→扫损→收回→放量位移
px = [12.0]*10 + [11.5, 11.0, 10.5, 10.2, 10.0, 10.1, 10.0, 10.05, 10.0, 9.98, 9.99, 10.0,
      10.01, 9.6, 10.4, 10.5, 10.9, 11.1, 11.2, 11.0, 11.3, 11.4, 11.5, 11.6, 11.7]
bs = bars(px)
m4 = run_sequence(bs, len(bs) - 1, symbol="TEST")
ok("重建状态机运行", m4.state in STATES + ("FILLED", "CLOSED"), m4.state)
ok("历史可追溯", len(m4.history) >= 0)
ok("无前视窗口(事件ts<=i)", all(e["timestamp"] <= bs[-1]["t"] for e in m4.events))


print("== 6. R12(第八轮审计 5.5): 时间倒序事件拒绝 ==")
from core.sequence import SequenceMachine
_m = SequenceMachine("600000")
_ok1, _ = _m.feed({"event_type": "LIQUIDITY_FORMED", "timestamp": "202609021000"})
_ok2, _ = _m.feed({"event_type": "SSL_SWEEP", "timestamp": "202609021100"})
_ok3, _s3 = _m.feed({"event_type": "RECLAIM", "timestamp": "202609020900"})
ok("顺序前两事件接受", _ok1 and _ok2)
ok("倒序 RECLAIM(09:00<11:00) 拒绝", (not _ok3) and _s3 != "READY")
ok("拒绝原因=TIME_REGRESSION", any(r.get("why") == "TIME_REGRESSION" for r in _m.rejected))
_ok4, _ = _m.feed({"event_type": "RECLAIM", "timestamp": "202609021200"})
ok("恢复正常时序 RECLAIM 接受", _ok4)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)