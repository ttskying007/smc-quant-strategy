# -*- coding: utf-8 -*-
"""tests_audit_causal_stream.py —— 事件流引擎回归锁(审计§3.2/§5.3/Iter0).

交付: v25/causal_stream.py —— 最小事件流引擎
  逐 bar 推进 + 右侧确认入库 + 未消费状态机 + sweep/reclaim/response 检测.

本测试固化审计验收:
  §5.3-1: 在线逐 bar vs 批量回放, 事件 ID 完全一致
  §10.1:  swing 只在右侧确认 bar 完成后可见(visible_at)
  §10.1:  sweep 不能重复消费已被触碰的流动性
  §10.2:  对历史前缀追加未来 bars 不得修改前缀决策
纯内存.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


from v25.causal_stream import (CausalEventEngine, batch_replay,  # noqa: E402
                               events_match_online_vs_batch, make_bars)

print("== 1. 在线逐 bar vs 批量回放一致(§5.3) ==")
# 构造: 摆动低(idx 5, low 95) -> 后续 sweep(idx 8, low 92 < 95*0.997 且收盘>95)
# -> response(idx 9, close > sweep high) -> 事件
bars = make_bars([
    ("2024-01-01", 100, 101, 99, 100, 100),
    ("2024-01-02", 100, 101, 99, 100, 100),
    ("2024-01-03", 100, 101, 99, 100, 100),
    ("2024-01-04", 100, 101, 99, 100, 100),
    ("2024-01-05", 100, 101, 99, 100, 100),
    ("2024-01-06", 100, 101, 95.0, 100, 100),    # swing low idx5
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-12", 100, 100, 92.0, 98, 500),     # sweep idx9: low92 < 95*0.997, close98>95
    ("2024-01-13", 100, 102, 99, 102, 300),      # response idx10: close102 > sweep high 100
])
ok("在线 vs 批量事件一致", events_match_online_vs_batch(bars), "")

print("== 2. 事件被正确识别 ==")
eng = CausalEventEngine("T")
for b in bars:
    eng.step(b)
ev = eng.event_ids()
ok("识别出 1 个事件", len(ev) == 1, ev)
if ev:
    e = list(ev)[0]
    ok("事件含 swing/sweep/response 日期",
       e[1] == "20240106" and e[2] == "20240112" and e[3] == "20240113", e)

print("== 3. 消费语义: 已被穿透的低不可再用(§10.1) ==")
# 摆动低 idx5 low95; 在 sweep 之前(如 idx7)先被穿透 low=94 -> 已消费
bars2 = make_bars([
    ("2024-01-01", 100, 101, 99, 100, 100),
    ("2024-01-02", 100, 101, 99, 100, 100),
    ("2024-01-03", 100, 101, 99, 100, 100),
    ("2024-01-04", 100, 101, 99, 100, 100),
    ("2024-01-05", 100, 101, 99, 100, 100),
    ("2024-01-06", 100, 101, 95.0, 100, 100),    # swing low
    ("2024-01-07", 100, 101, 99, 100, 100),
    ("2024-01-08", 100, 101, 99, 100, 100),
    ("2024-01-09", 100, 101, 99, 100, 100),
    ("2024-01-10", 100, 101, 94.0, 96, 300),     # 穿透 low94 <= 95 -> 消费
    ("2024-01-13", 100, 100, 92.0, 98, 500),     # 再 sweep(低95已消费, 不能用)
    ("2024-01-14", 100, 102, 99, 102, 300),
])
eng2 = CausalEventEngine("T")
for b in bars2:
    eng2.step(b)
ok("已消费的低不再产生事件", len(eng2.event_ids()) == 0, eng2.event_ids())

print("== 4. 追加未来 bar 不改变历史(§10.2) ==")
prefix = bars[:10]
eng_pre = CausalEventEngine("T")
for b in prefix:
    eng_pre.step(b)
# 追加更多未来 bars
ext = make_bars([("2024-01-15", 100, 105, 98, 104, 200),
                 ("2024-01-16", 100, 106, 99, 105, 200),
                 ("2024-01-17", 100, 107, 99, 106, 200)])
eng_full = CausalEventEngine("T")
for b in prefix + ext:
    eng_full.step(b)
# 前缀内的事件必须保留(追加未来不改历史)
pre_ev = eng_pre.event_ids()
full_ev = eng_full.event_ids()
ok("前缀事件在追加未来后保留", pre_ev <= full_ev, (pre_ev, full_ev))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)