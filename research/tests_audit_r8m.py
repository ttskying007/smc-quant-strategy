# -*- coding: utf-8 -*-
"""tests_audit_r8m.py —— R24(第八轮审计 P1-2 落地 + P1-1 stale 确认)回归锁:
① P1-2: 开盘窗口守卫(09:30-10:15 上海)——next_open/limit_or_open open_fallback/
   legacy retrace 三模式全覆盖; 窗口过后 MISSED_OPEN 不回溯; 无 now 向后兼容;
   limit_retrace 严格限价不受窗口影响;
② 生产 snapshot 带 now(paper_sim monitor fill 链);
③ P1-1 stale 确认: realtime_prices 已透传 high/low + try_exit 已消费极值
   (SL 用 px_low 优先于 TP 的 px_high 保守序) —— 第七轮已修, 本轮锁定。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

from core.execution import try_fill, try_exit, _missed_open_window

print("== 1. P1-2: 开盘窗口守卫 ==")
_o_next = {"code": "600000", "entry_mode": "next_open", "reference_price": 10.0, "valid_from": ""}
_s_in = {"px": 10.5, "open": 10.3, "today": "20260914", "now": "2026-09-14 09:45:00"}
_s_out = {"px": 10.5, "open": 10.3, "today": "20260914", "now": "2026-09-14 10:30:00"}
ok("next_open 窗口内成交", try_fill(_o_next, _s_in).get("filled") is True)
r = try_fill(_o_next, _s_out)
ok("next_open 窗口后 MISSED_OPEN", r.get("filled") is False and r.get("why") == "MISSED_OPEN", r)
ok("MISSED_OPEN 带说明", "09:30-10:15" in (r.get("note") or ""))
# 边界: 09:30 恰在窗口 / 10:15 恰在窗口 / 10:16 出窗
ok("09:30 恰窗口边界内", try_fill(_o_next, {**_s_in, "now": "2026-09-14 09:30:00"}).get("filled") is True)
ok("10:15 恰窗口边界内", try_fill(_o_next, {**_s_in, "now": "2026-09-14 10:15:00"}).get("filled") is True)
ok("10:16 出窗 MISSED", try_fill(_o_next, {**_s_in, "now": "2026-09-14 10:16:00"}).get("why") == "MISSED_OPEN")
ok("13:00 午后 MISSED", try_fill(_o_next, {**_s_in, "now": "2026-09-14 13:00:00"}).get("why") == "MISSED_OPEN")
ok("14:55 尾盘 MISSED", try_fill(_o_next, {**_s_in, "now": "2026-09-14 14:55:00"}).get("why") == "MISSED_OPEN")
# limit_or_open: 触价优先(窗口后仍可成交——触价是盘中持续语义)
_o_lo = {"code": "600000", "entry_mode": "limit_or_open", "reference_price": 10.2, "valid_from": ""}
ok("limit_or_open 窗口后触价仍成交(盘中回踩)", 
   try_fill(_o_lo, {**_s_out, "low": 10.1}).get("fill_rule") == "LIMIT_OR_OPEN: low<=ref")
ok("limit_or_open 窗口后未触价 MISSED_OPEN",
   try_fill(_o_lo, _s_out).get("why") == "MISSED_OPEN")
ok("limit_or_open 窗口内未触价 open_fallback",
   try_fill(_o_lo, _s_in).get("fill_rule") == "LIMIT_OR_OPEN: open_fallback")
# legacy retrace 同守卫
_o_lr = {"code": "600000", "entry_mode": "retrace", "reference_price": 9.8, "valid_from": ""}
_r_lr = try_fill(_o_lr, _s_out)
ok("legacy retrace 窗口后 open 兜底 MISSED", _r_lr.get("why") == "MISSED_OPEN" and
   _r_lr.get("order_type") == "LEGACY_RETRACE", _r_lr)
# limit_retrace 严格限价: 未触价 PENDING(窗口无关)
_o_lrt = {"code": "600000", "entry_mode": "limit_retrace", "reference_price": 9.8, "valid_from": ""}
ok("limit_retrace 未触价窗口后仍 WAIT_RETRACE",
   try_fill(_o_lrt, _s_out).get("why") == "WAIT_RETRACE")
ok("limit_retrace 触价窗口后仍成交",
   try_fill(_o_lrt, {**_s_out, "low": 9.7}).get("fill_rule") == "LIMIT_RETRACE: low<=ref")

print("== 2. 无 now 向后兼容 + helper ==")
ok("无 now → 不判定(False)", _missed_open_window({"px": 10}) is False)
ok("helper 窗口内 False", _missed_open_window({"now": "2026-09-14 09:31:00"}) is False)
ok("helper 窗口后 True", _missed_open_window({"now": "2026-09-14 11:00:00"}) is True)
ok("helper 解析失败 fail-open", _missed_open_window({"now": "garbage"}) is False)
ok("quote_ts 别名识别", _missed_open_window({"quote_ts": "2026-09-14 11:00:00"}) is True)

print("== 3. 生产链 snapshot 带 now ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("monitor fill 快照带 now", '_snap["now"] = cn_now(' in src_ps)
ok("P1-2 注释在(第八轮)", "第八轮审计 P1-2" in src_ps)

print("== 4. P1-1 stale 确认(第七轮已修, 锁定) ==")
ok("realtime_prices 透传 high/low", '"high": _high, "low": _low' in src_ps)
src_ex = open(os.path.join(HERE, "core", "execution.py"), encoding="utf-8").read()
ok("try_exit 消费极值 px_high/px_low", "px_high = max(float(px), float(_hi))" in src_ex)
ok("SL 用 px_low(保守优先)", "if px_low <= active_sl:" in src_ex and
   src_ex.find("px_low <= active_sl") < src_ex.find("px_high >= tp1"))
ok("monitor 退出快照透传 _info(含 high/low)", '_snap4core = dict(_info or {})' in src_ps)

print("== 5. R12-R23 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src_ps)
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("ADX 单源入口仍在", "from core.indicators import adx14_of as _adx_core" in src_ps)
ok("时区单源仍在", "from core.time_cn import cn_now, cn_today" in src_ps)
ok("limit_pct_for 诚实化保持", "不含 ST 判定" in src_ex)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)