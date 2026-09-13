# -*- coding: utf-8 -*-
"""tests_audit_r8g.py —— R18(第八轮审计 P1-9)成交前二次校验回归锁:
① monitor fill 分支 FILLED 确认前过 gate(组合状态含本单成交后);
② CAPACITY_REJECT_FILL 撤单路径(EXPIRED + not_filled_reason + 日志);
③ 枚举注册(EXPIRE_REASONS 三成员);
④ gate 纯函数行为(模拟成交时点状态变化)。
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

src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()

print("== 1. 成交前 gate 接线(源码契约) ==")
ok("FILLED 确认前 gate 调用存在", "R18成交前gate" in src_ps)
ok("组合状态含本单成交后模拟", '"position_pct": float(t.get("position_pct") or 0.01)}' in src_ps)
ok("其余 PENDING 保持潜在暴露", '_others = [t2 for t2 in led if t2.get("status") in ("PENDING_ORDER", "FILLED")' in src_ps)
ok("单日新开按成交日计", 't2.get("filled_at", "").startswith(_today)' in src_ps)
ok("gate 拒绝 → EXPIRED + CAPACITY_REJECT_FILL", 't["expire_reason"] = "CAPACITY_REJECT_FILL"' in src_ps)
ok("not_filled_reason 同步(CAPACITY_REJECT_FILL)", 't["not_filled_reason"] = "CAPACITY_REJECT_FILL"' in src_ps)
ok("实时日志撤单记录", '"note": f"CAPACITY_REJECT_FILL({_gate_why})"' in src_ps)
ok("gate 异常不阻断成交(创建前已过一次)", '_gate_ok = True  # gate 自身异常不阻断成交' in src_ps)

print("== 2. 枚举注册 ==")
from core.reason_enums import EXPIRE_REASONS, EXP_CAPACITY_REJECT_FILL
ok("CAPACITY_REJECT_FILL ∈ EXPIRE_REASONS", EXP_CAPACITY_REJECT_FILL in EXPIRE_REASONS, sorted(EXPIRE_REASONS))
ok("EXPIRE_REASONS 三成员", len(EXPIRE_REASONS) == 3, sorted(EXPIRE_REASONS))

print("== 3. gate 纯函数: 成交时点状态变化场景 ==")
from core.portfolio import portfolio_exposure_check, throttle_open
# 场景A: 创建时 0.7 合规, 其它单先成交 0.3 → 成交时点 0.7+0.3+本单 0.2 = 1.2 > 0.8 拒
_pos_others = [{"code": "A", "position_pct": 0.7}, {"code": "B", "position_pct": 0.3}]
_pos_after = _pos_others + [{"code": "C", "position_pct": 0.2}]
_gA, _wA, _tA = portfolio_exposure_check(_pos_after)
ok("创建后其它单成交 → 总暴露 1.2 超 0.8 → 拒", not _gA, (_wA, _tA))
# 场景B: 正常状态 → 通过
_gB, _wB, _ = portfolio_exposure_check([{"code": "A", "position_pct": 0.2}, {"code": "C", "position_pct": 0.15}])
ok("正常成交时点组合 → 通过", _gB, _wB)
# 场景C: 单日新开——已 4 笔今日成交 + 本单 = 5 ≤ 5 合规; 5 笔 + 本单 = 6 拒
_gC1, _ = throttle_open([True] * 4, {}, max_daily_opens=5)[:2]
_gC2, _ = throttle_open([True] * 5, {}, max_daily_opens=5)[:2]
ok("今日已成交 4 + 本单 → 合规", _gC1 is True)
ok("今日已成交 5 + 本单 → 拒(MAX_DAILY_OPEN)", _gC2 is False)

print("== 4. R12-R17 修复保持 ==")
ok("创建前 gate 仍在(CAPACITY_REJECT)", '"stage": "CAPACITY_REJECT"' in src_ps)
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("shadow_replay 存在", os.path.exists(os.path.join(HERE, "shadow_replay.py")))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)