# -*- coding: utf-8 -*-
"""tests_audit_r8r.py —— R29(第八轮审计 P1-3 剩余差异)回归锁:
② tp3 透传消费(与 simulate 同条件对齐); ③ tp1_hit 后 TIME_STOP 不再跳过。
审计原文复现(差异③): "position: ep=10, sl=9, tp1=0, tp2=0, bars_since_fill=20
→ try_exit: TIME_STOP" —— 但更隐蔽的是 tp1_hit=True 的仓永远等不到时间
止损(死等 TP2/SL 可拖至远超 max_hold)。simulate 的 TIME_STOP 对剩余仓
一视同仁。
差异②(原写法说明): tp3 与 TP2 同轮触发时 TP2 先(逐 bar/逐轮先触先出,
 simulate TP2 break 在前) —— tp3 直达只在 **tp2 缺失**(单目标 tp3 语义,
 无 tp2)时真实生效, 与 simulate L175 'not tp2 or tp3 > tp2' 镜像。
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

from core.execution import try_exit

print("== 1. 差异③: tp1_hit 后 TIME_STOP(审计复现修复) ==")
pos_be = {"code": "600000", "filled_price": 10.0, "sl": 9.0, "tp1": 10.5, "tp2": 11.0,
          "tp1_hit": True, "tp3": 0, "filled_at": "2026-09-10", "max_hold": 12}
# TP1 部分平后, bars=20>12 → 剩余仓 TIME_STOP(原死等 TP2/SL)
r = try_exit(pos_be, {"px": 10.3, "today": "20260914", "bars_since_fill": 20})
ok("tp1_hit+bars=20 → TIME_STOP(修复)", r.get("reason") == "TIME_STOP", r)
# TP1 后仍在持有期内 → HOLD(保本底 sl=max(ep,sl) 由 SL 分支管)
r_h = try_exit(pos_be, {"px": 10.3, "today": "20260914", "bars_since_fill": 5})
ok("tp1_hit+bars=5 → HOLD(期内)", r_h.get("why") == "HOLD", r_h)
# TP1 后超期但同轮触 TP2 → TP2 优先(先触先出)
r_t2 = try_exit(pos_be, {"px": 11.2, "today": "20260914", "bars_since_fill": 20, "high": 11.2})
ok("tp1_hit+超期+触TP2 → TP2 优先", r_t2.get("reason") == "TP2_RUNNER", r_t2)

print("== 2. 差异②: tp3 透传消费 ==")
# tp2 缺失 + tp3 有值(单目标 tp3 语义) → tp3 直达生效
pos_t3 = {"code": "600003", "filled_price": 10.0, "sl": 9.0, "tp1": 10.5,
          "tp1_hit": True, "filled_at": "2026-09-10", "tp3": 11.5}
r3 = try_exit(pos_t3, {"px": 11.6, "today": "20260914", "bars_since_fill": 5, "high": 11.6})
ok("tp2 缺失+tp3 直达 → TP3_RUNNER", r3.get("reason") == "TP3_RUNNER", r3)
ok("TP3_RUNNER 价格含卖滑", r3.get("price") and r3["price"] < 11.6, r3)
# tp2 存在时同轮先 TP2(两路径一致: 逐 bar/逐轮先触先出)
pos_t23 = {**pos_t3, "tp2": 11.0}
r23 = try_exit(pos_t23, {"px": 11.6, "today": "20260914", "bars_since_fill": 5, "high": 11.6})
ok("tp2 在场同轮 → TP2 先(一致)", r23.get("reason") == "TP2_RUNNER", r23)
# tp3 未触 → HOLD
r3h = try_exit(pos_t3, {"px": 11.0, "today": "20260914", "bars_since_fill": 5})
ok("tp3 未触 → HOLD", r3h.get("why") == "HOLD", r3h)
# paper_sim 透传源码
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("paper_sim 透传 tp3", '"tp3": t.get("tp3")' in src_ps)
ok("R29 注释在(差异②)", "R29(第八轮 P1-3 差异②)" in src_ps)

print("== 3. 既有语义保持(回归) ==")
# 单目标 CONT(tp1=0) tp2 全平
r_c = try_exit({"code": "600001", "filled_price": 10.0, "sl": 9.0, "tp1": 0, "tp2": 11.5,
                "tp1_hit": False, "filled_at": "2026-09-10"},
               {"px": 11.6, "today": "20260914", "bars_since_fill": 3, "high": 11.6})
ok("单目标 CONT TP2_RUNNER 保持", r_c.get("reason") == "TP2_RUNNER")
# 未 tp1_hit 超时 TIME_STOP(原审计复现例) 保持
r_ts = try_exit({"code": "600002", "filled_price": 10.0, "sl": 9.0, "tp1": 10.5, "tp2": 11.0,
                 "tp1_hit": False, "filled_at": "2026-09-10"},
                {"px": 10.2, "today": "20260914", "bars_since_fill": 15})
ok("未TP1 超时 TIME_STOP 保持", r_ts.get("reason") == "TIME_STOP")
# T+1 锁定保持
r_t1 = try_exit({"code": "600004", "filled_price": 10.0, "sl": 9.0, "filled_at": "2026-09-14",
                 "tp1_hit": False},
                {"px": 10.5, "today": "20260914"})
ok("T+1 锁定保持", r_t1.get("why") == "T1_LOCKED")
# SL 优先序保持(px_low<=sl 即出, 即便 px_high 也触 tp1)
r_sl = try_exit({"code": "600005", "filled_price": 10.0, "sl": 9.0, "tp1": 10.5,
                 "tp1_hit": False, "filled_at": "2026-09-10"},
                {"px": 9.9, "low": 8.9, "high": 10.6, "today": "20260914"})
ok("SL 优先(同轮双触)保持", r_sl.get("reason") in ("SL_HIT", "SL_GAP"))
# 枚举: TP3_RUNNER 在 SIM 族
from core.reason_enums import SIM_REASONS
ok("TP3_RUNNER 已在枚举", "TP3_RUNNER" in SIM_REASONS)

print("== 4. R12-R28 修复保持 ==")
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("R27 时段守卫仍在", "R27 交易时段守卫" in src_ps)
ok("R25 空价 TTL 仍在", "R25 TTL(行情不可用推进)" in src_ps)
ok("R26 monitor now 仍在", '_snap["now"] = cn_now(' in src_ps)
ok("R24 开盘窗口守卫仍在", "_missed_open_window" in open(os.path.join(HERE, "core", "execution.py"), encoding="utf-8").read())

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)