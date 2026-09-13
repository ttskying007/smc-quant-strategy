# -*- coding: utf-8 -*-
"""tests_audit_r8d.py —— R15(第八轮审计)第四批修复回归锁:
① P1-12 北交所前缀映射(bj)+ bars_of 北交所边界(缓存无该数据源);
② 5.1 h_layer_model=H_PROJECTED_DAILY 显式标注;
③ P1-9 PortfolioGate 订单创建前接线(总暴露/单日/持仓/kill switch → CAPACITY_REJECT)
   + CAPACITY_REJECT ∈ REJECT_STAGES + _tri_decompose 守恒含 capacity。
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

print("== 1. P1-12: 北交所前缀 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("realtime_prices 映射含 bj 分支", 'ex = "bj"' in src_ps)
ok("bars_of 北交所显式返回空(数据源边界)", 'startswith(("4", "8", "9")) and len(code) == 6' in src_ps)
# 功能验证: 前缀函数行为
import paper_sim as PS
ok("bars_of('830001') 返回空(北交所无缓存)", PS.bars_of("830001") == [])
ok("bars_of('600519') 不受影响(有缓存)", len(PS.bars_of("600519")) > 0)

print("== 2. 5.1: H_PROJECTED_DAILY 标注 ==")
_w = os.path.normpath(os.path.join(HERE, "..", "wdh", "wdh_engine.py"))
src_w = open(_w, encoding="utf-8").read()
ok("seeds 含 h_layer_model 字段", '"h_layer_model": "H_PROJECTED_DAILY"' in src_w)
ok("标注注释存在(不得宣称完整 H 层)", "不得宣称完整 H 层验证" in src_w)

print("== 3. P1-9: PortfolioGate 接线 ==")
ok("订单创建前 gate 调用存在", "portfolio_exposure_check" in src_ps and "throttle_open" in src_ps)
ok("kill_switch 调用存在", "kill_switch as _ks" in src_ps)
ok("CAPACITY_REJECT 拒单分支", 't["status"]' not in "" and '"stage": "CAPACITY_REJECT"' in src_ps)
ok("capacity_reject 统计计数", '_sel_stats["capacity_reject"]' in src_ps)
# 枚举注册
from core.reason_enums import REJECT_STAGES, REJ_CAPACITY_REJECT
ok("CAPACITY_REJECT ∈ REJECT_STAGES", REJ_CAPACITY_REJECT in REJECT_STAGES, sorted(REJECT_STAGES))
# _tri_decompose 守恒: raw = quality + nodata + dup + capacity + orders
_td = PS._tri_decompose(raw=10, hard=1, soft=1, soft_delta=1, skipped_stage=1, skipped_adx=1,
                        nodata=1, dup=1, orders=1, bad_sl=1, capacity=1)
q = _td["quality_reject"]; cap = _td["execution_capacity"]
ok("守恒: 10 = 6(quality含bad_sl1) + 1(nodata) + 1(dup) + 1(capacity) + 1(orders)",
   q + _td["data_missing"] + cap["dup"] + cap["portfolio_gate"] + _td["orders_created"] == 10, _td)
ok("portfolio_gate 计数=1(非0)", cap["portfolio_gate"] == 1, cap)
ok("守恒注释含 portfolio_gate", "portfolio_gate" in _td["conservation_note"])
# gate 纯函数行为(独立验证)
from core.portfolio import portfolio_exposure_check, throttle_open, kill_switch
_ok1, _w1, _t1 = portfolio_exposure_check([{"code": "A", "position_pct": 0.3},
                                           {"code": "B", "position_pct": 0.6}])
ok("总暴露 0.9>0.8 → 拒绝", not _ok1, (_w1, _t1))
_ok2, _w2, _ = portfolio_exposure_check([{"code": "A", "position_pct": 0.5}])
ok("单票 0.5>0.25 → 拒绝", not _ok2, _w2)
_ok3, _w3, _ = portfolio_exposure_check([{"code": "A", "position_pct": 0.2},
                                         {"code": "B", "position_pct": 0.2}])
ok("总暴露 0.4 合规 → OK", _ok3, _w3)
_g1, _gw1 = throttle_open([True]*10, {}, max_positions=10)
ok("持仓已满 10 → MAX_POSITIONS 拒", not _g1 and _gw1 == "MAX_POSITIONS", (_g1, _gw1))
_g2, _gw2 = throttle_open([], {"主板": 3})
ok("板块 3 → MAX_SECTOR 拒", not _g2 and _gw2 == "MAX_SECTOR", (_g2, _gw2))
_g3, _gw3 = throttle_open([True]*5, {}, max_daily_opens=5)
ok("单日开仓已 5 → MAX_DAILY_OPEN 拒", not _g3 and _gw3 == "MAX_DAILY_OPEN", (_g3, _gw3))
_ksr = kill_switch([-0.02] * 20, window="daily")
ok("近20笔 -40% → kill switch 触发", _ksr[0] is True, _ksr)
_ksr2 = kill_switch([0.01, -0.001], window="daily")
ok("正常收益 → 不触发", _ksr2[0] is False, _ksr2)

print("== 4. R12-R14 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("CONT tp2 接线仍在", '"tp2": round(tp, 3),' in src_ps)
src_seq = open(os.path.join(HERE, "core", "sequence.py"), encoding="utf-8").read()
ok("RETEST_HOLD 仍在", '"RETEST_HOLD"' in src_seq)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)