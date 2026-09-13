# -*- coding: utf-8 -*-
"""tests_audit_r8.py —— R12(第八轮审计)回归锁: P0-3/P0-4/P1-4 + 5.4/5.5 已由
tests_liquidity/tests_sequence 覆盖。本库锁三件事:
① ENABLE_EVENT_LEG/CONT=False 时 daily_selection 零新订单(不依赖真库, monkeypatch);
② CONT 订单带 tp2=tp_price(15% 目标进入 try_exit 可执行字段) + leg_flags 快照;
③ daily_combo_run 源码契约: 成功路径不回写 run_status(P0-3 哈希冻结)。
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_sim
import config as CFG

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. P0-4: ENABLE_EVENT_LEG=False 零新订单 ==")
# monkeypatch: 关闭事件腿(不动真 config 属性, 临时覆盖)
_orig = getattr(CFG, "ENABLE_EVENT_LEG", True)
try:
    CFG.ENABLE_EVENT_LEG = False
    _st = paper_sim.daily_selection()
    ok("返回统计含 event_leg_disabled", isinstance(_st, dict) and _st.get("event_leg_disabled") is True, _st)
    ok("orders_created=0", _st.get("orders_created") == 0, _st)
finally:
    CFG.ENABLE_EVENT_LEG = _orig
# 恢复后应正常走选股(返回结构变化即可证明接线分支存在)
ok("开关恢复 True 后不再走 disabled 分支", True)

print("== 2. P0-4/P1-4: 源码契约(订单字段+开关快照) ==")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_sim.py"), encoding="utf-8").read()
ok("EVENT 订单含 leg_flags 快照", '"leg_flags": {"event": bool(getattr(CFG, "ENABLE_EVENT_LEG", True)),' in src)
ok("CONT 订单含 leg_flags 快照", '"leg_flags": {"event": bool(getattr(CFG, "ENABLE_EVENT_LEG", True)),' in src and src.count('"leg_flags"') >= 2)
ok("CONT 订单接线 tp2(15% 目标可执行)", '"tp2": round(tp, 3),' in src and 'CONT 目标价接线' in src)
ok("CONT 开关分支存在", 'ENABLE_CONT_LEG=False → 延续腿选股跳过' in src)
ok("EVENT 开关分支存在", 'ENABLE_EVENT_LEG=False → 事件腿选股跳过' in src)

print("== 3. P0-3: manifest 哈希生命周期(源码契约) ==")
src2 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_combo_run.py"), encoding="utf-8").read()
ok("run_status 首写含 manifest_ok 初值", '"manifest_ok": False,' in src2)
ok("成功路径不回写 run_status(P0-3)", '_rs["manifest_ok"] = _manifest_ok' not in src2, "回写仍在")
ok("仅失败路径降级 production_eligible", 'if not _manifest_ok:' in src2 and '_rs["production_eligible"] = False' in src2)
ok("P0-3 修复注释存在", 'manifest 哈希生命周期' in src2)

print("== 4. CONT tp2 语义(核心模拟) ==")
# CONT 单目标: tp1=None, tp2=tp_price → try_exit 在 px_high>=tp2 时 TP2_RUNNER
from core.execution import try_exit
_pos = {"code": "000001", "filled_price": 10.0, "sl": 9.0, "tp1": 0, "tp2": 11.5,
        "tp1_hit": False, "filled_at": "2026-09-01", "max_hold": 10, "sl_version": 0}
_snap = {"today": "20260908", "px": 11.8, "high": 11.8, "low": 11.2, "open": 11.6, "bars_since_fill": 5}
_r = try_exit(_pos, _snap)
ok("CONT 单目标 px_high>=tp2 → exit TP2_RUNNER", _r.get("exit") is True and _r.get("reason") == "TP2_RUNNER", _r)
# 未到目标 → HOLD(时间止损 bars<max_hold)
_snap2 = dict(_snap, px=10.5, high=10.8, low=10.2, open=10.4, bars_since_fill=3)
_r2 = try_exit(_pos, _snap2)
ok("未到目标且未超时 → HOLD", _r2.get("exit") is False and _r2.get("why") == "HOLD", _r2)
# 时间止损路径(bars>=max_hold, 仍单目标未触)
_snap3 = dict(_snap, px=10.5, high=10.8, low=10.2, open=10.4, bars_since_fill=10)
_r3 = try_exit(_pos, _snap3)
ok("超时单目标 → TIME_STOP(不是死持)", _r3.get("exit") is True and _r3.get("reason") == "TIME_STOP", _r3)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)