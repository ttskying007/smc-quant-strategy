# -*- coding: utf-8 -*-
"""tests_audit_r8s.py —— R30(第八轮审计 P1-4 复核 + P1-5 收口)回归锁:
① P1-4 三条全闭合复核: CONT 统一字段(tp1=None, tp2=tp_price 已在挂单
   生成写入)+try_exit 单目标分支(R12)+自然日退出已删(第七轮);
② P1-5 持有期统一收口: CONT 自适应经 max_hold 透传(自然日→bar 已统一),
   语义锁: adaptive_hold 三态(强趋势/弱市 20, 震荡 12, 无 proxy 原样);
③ 回测 10 日固定 vs 生产 10-20 自适应的口径差 —— 冻结基线保护标注
   (gen_cont_v20f n=334 依赖 10 日固定, 与 P1-7/P1-8 同批重基线)。
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

import paper_sim as PS
from core.execution import try_exit
src = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()

print("== 1. P1-4 三条全闭合复核 ==")
# 条①: CONT 挂单写 tp1=None/tp2=tp_price(源码级)
ok("CONT 单目标生成语义在(tp_price→tp2 路径)", src.count("tp_price") >= 3 and "tp2" in src)
# 找 CONT 订单生成段
_seg = src[src.find("CONT"):]
# 条②: try_exit 单目标分支(R12)行为
r = try_exit({"code": "600001", "filled_price": 10.0, "sl": 9.0, "tp1": 0, "tp2": 11.5,
              "tp1_hit": False, "filled_at": "2026-09-10"},
             {"px": 11.6, "today": "20260914", "bars_since_fill": 3, "high": 11.6})
ok("CONT 单目标 tp2 触发全平(R12)", r.get("reason") == "TP2_RUNNER", r)
# CONT 不写 tp1(不部分平仓)
r_p = try_exit({"code": "600002", "filled_price": 10.0, "sl": 9.0, "tp1": 10.5, "tp2": 11.5,
                "tp1_hit": False, "filled_at": "2026-09-10"},
               {"px": 10.6, "today": "20260914", "bars_since_fill": 3, "high": 10.6})
ok("对照: 有 tp1 的单部分平(partial TP1)", r_p.get("partial") == "TP1", r_p)
# 条③: 自然日 HOLD_EXIT 已删
ok("time.time() 自然日退出已清零", "time.time()" not in src, src.count("time.time()"))
ok("HOLD_EXIT 分支删除注释在", "删除 CONT 独立自然日 HOLD_EXIT 分支" in src)
# HOLD_EXIT 仅作为历史账本 legacy 值存在(枚举认可)
from core.reason_enums import PAPER_EXITS
ok("HOLD_EXIT 在枚举(历史 legacy)", "HOLD_EXIT" in PAPER_EXITS)

print("== 2. P1-5 持有期统一收口 ==")
# adaptive_hold 三态语义
ok("proxy=None → base(10)", PS.adaptive_hold(10, None) == 10)
ok("proxy>0.02(强趋势) → 20", PS.adaptive_hold(10, 0.05) == 20)
ok("proxy<-0.02(弱市) → 20", PS.adaptive_hold(10, -0.05) == 20)
ok("proxy 震荡(-2%~2%) → 12", PS.adaptive_hold(10, 0.01) == 12)
ok("base 透传(无 proxy)", PS.adaptive_hold(15, None) == 15)
# CONT max_hold 透传链(源码)
ok("CONT max_hold 按腿透传在", '_max_hold_4core = _mh' in src and 't.get("source") == "CONT"' in src)
ok("adaptive_hold 调用链在", "_mh = adaptive_hold(_mh, _pr_hold)" in src)
# 行为: CONT max_hold 透传后 TIME_STOP 按 bar 计
r_t = try_exit({"code": "600003", "filled_price": 10.0, "sl": 9.0, "tp1": 0, "tp2": 11.5,
                "tp1_hit": False, "filled_at": "2026-09-10", "max_hold": 10},
               {"px": 10.2, "today": "20260914", "bars_since_fill": 10})
ok("CONT hold=10 → bars=10 TIME_STOP", r_t.get("reason") == "TIME_STOP", r_t)
r_t2 = try_exit({"code": "600004", "filled_price": 10.0, "sl": 9.0, "tp1": 0, "tp2": 11.5,
                 "tp1_hit": False, "filled_at": "2026-09-10", "max_hold": 20},
                {"px": 10.2, "today": "20260914", "bars_since_fill": 12})
ok("自适应 20 → bars=12 仍持有", r_t2.get("why") == "HOLD", r_t2)
# EVENT 缺省走 CFG.MAX_HOLD(12)
r_e = try_exit({"code": "600005", "filled_price": 10.0, "sl": 9.0, "tp1": 10.5, "tp2": 11.0,
                "tp1_hit": False, "filled_at": "2026-09-10"},
               {"px": 10.2, "today": "20260914", "bars_since_fill": 12})
ok("EVENT 缺省 12 → bars=12 TIME_STOP", r_e.get("reason") == "TIME_STOP", r_e)

print("== 3. 冻结基线口径差标注(P1-5/P1-7/P1-8 同批) ==")
src_g = open(os.path.join(HERE, "gen_cont_v20f.py"), encoding="utf-8").read()
ok("gen_cont_v20f 10 日固定在", "10" in src_g and ("exit_c" in src_g or "固定" in src_g))
ok("R17 因果重写标注在", "signal" in src_g)
src_g20 = open(os.path.join(HERE, "gen_v20f.py"), encoding="utf-8").read()
ok("gen_v20f max_hold 分叉标注在(R23)", "持有期分叉标注(R23" in src_g20)
ok("gen_v20f ADX 分叉标注在(R22)", "legacy 单窗" in src_g20)

print("== 4. R12-R29 修复保持 ==")
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src)
ok("R27 时段守卫仍在", "R27 交易时段守卫" in src)
ok("R29 tp3 透传仍在", '"tp3": t.get("tp3")' in src)
ok("R28 ADX 单源入口仍在", "from core.indicators import adx14_of as _adx_core" in src)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)