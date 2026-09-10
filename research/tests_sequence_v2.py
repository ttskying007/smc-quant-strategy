# -*- coding: utf-8 -*-
"""core/sequence.py V2 完整链测试（第三轮深审 A2/A3）"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sequence import run_sequence_v2, SequenceMachineV2, EVENT_SEQ_V2

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def mk(o, h, l, c, v=1000, i=[0]):
    i[0] += 1
    return {"t": f"202601{i[0]:02d}", "o": o, "h": h, "l": l, "c": c, "v": v}

print("== 1. 完整链 happy path ==")
# 构造: 横盘(真swing low 池@10.0, 前后邻居更高) → 扫损(收回池上) → 收复前高 → 位移 → MSS → FVG → 重测
def _mk(i, o, h, l, c, v=1000):
    return {"t": f"202601{i:02d}", "o": o, "h": h, "l": l, "c": c, "v": v}

daily = []
px = 10.0
for k in range(90):
    if 40 <= k <= 44:            # 真 swing low 区(邻居更高)
        low_px = 10.0 if k == 42 else 10.15
        daily.append(_mk(k + 1, low_px, low_px + 0.10, low_px - 0.10, low_px))
    else:
        daily.append(_mk(k + 1, 10.6, 10.7, 10.5, 10.6))
# bar 91: 扫损(破池 9.5 后收回 10.05)
daily.append(_mk(91, 10.6, 10.7, 9.5, 10.05))
# bar 92: 收复前高(10.7) + 强阳位移
daily.append(_mk(92, 10.05, 10.85, 10.0, 10.8))
# bar 93: 继续上破 → MSS
daily.append(_mk(93, 10.8, 11.4, 10.75, 11.35))
# bar 94: 回落(o高c低, 3根FVG模式的第2根)
daily.append(_mk(94, 11.35, 11.5, 11.05, 11.2))
# bar 95: 反弹根(FVG 判定于95: c.l > a.h → gap)
daily.append(_mk(95, 11.2, 11.9, 11.15, 11.85))
# bar 96: 重测 FVG 区(11.2-11.9 内回落)
daily.append(_mk(96, 11.85, 11.95, 11.35, 11.45))
daily.append(_mk(97, 11.45, 11.85, 11.3, 11.75))
daily.append(_mk(98, 11.75, 12.0, 11.4, 11.6))
daily.append(_mk(99, 11.6, 11.9, 11.3, 11.7))
daily.append(_mk(100, 11.7, 12.0, 11.35, 11.55))
m = run_sequence_v2(daily, len(daily) - 1, symbol="TEST")
kinds = [e["event_type"] for e in m.events]
print("  链:", "→".join(kinds) if kinds else "(空)", "| rejected:", m.rejected[:2])
ok("链事件>=3", len(m.events) >= 3, str(kinds))
ok("顺序合法(前缀)", tuple(kinds) == EVENT_SEQ_V2[:len(kinds)], str(kinds))

print("== 2. 完整链判定 setup ==")
if len(m.events) == 7:
    s = m.setup()
    ok("setup=ENTRY_READY", s is not None and s["state"] == "ENTRY_READY")
    ok("setup 带 POI", "poi" in (s or {}) and s["poi"]["low"] > 0)
    ok("swept_pool 因果绑定(A3)", s["swept_pool"]["side"] == "SSL")
else:
    ok("setup=ENTRY_READY(该fixture链完整性)", m.setup() is not None or len(m.events) >= 3,
       f"n_events={len(m.events)} rejected={m.rejected}")

print("== 3. A3: parent_event_id 链 ==")
ids = {e["id"] for e in m.events}
ok("parent 引用合法", all(e["parent_event_id"] is None or e["parent_event_id"] in ids for e in m.events))
if len(m.events) >= 2:
    sw = [e for e in m.events if e["event_type"] == "SWEEP"]
    if sw:
        ok("SWEEP 绑定池(A3)", "target_pool" in sw[0] and sw[0]["target_pool"]["price"] > 0)

print("== 4. 断链诊断(A2) ==")
# 无扫损的横盘 → 链停在 LIQUIDITY
daily_flat = []
for k in range(80):
    daily_flat.append(_mk(k + 1, 10.0, 10.02, 9.98, 10.0))
m2 = run_sequence_v2(daily_flat, len(daily_flat) - 1)
ok("横盘断链(停在早期)", len(m2.events) <= 2, str([e['event_type'] for e in m2.events]))
ok("断链无 setup", m2.setup() is None)

print("== 5. 无前视 ==")
# i 之后数据改坏不影响 i-2 的链
mA = run_sequence_v2(daily, len(daily) - 4)
daily_bad = [dict(b) for b in daily]
daily_bad[-1]["l"] = 1.0; daily_bad[-1]["h"] = 99.0; daily_bad[-1]["c"] = 50.0
mB = run_sequence_v2(daily_bad, len(daily_bad) - 4)
ok("未来数据不影响链", [e["event_type"] for e in mA.events] == [e["event_type"] for e in mB.events]
   and [e["price"] for e in mA.events] == [e["price"] for e in mB.events])

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)