# -*- coding: utf-8 -*-
"""统一执行三函数测试（审计 P0-4）：plan_order / try_fill / try_exit。
验证：回测(simulate)与纸面(实时快照)共用同一套执行语义，判定顺序一致。"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.execution as EX

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + detail)

print("== 1. plan_order：信号只产生计划，不写死成交价 ==")
sig = {"code": "000001", "name": "平安银行", "signal_date": "20260904",
       "entry_ref": 10.0, "sl": 9.5, "tp": 11.5, "valid_from": "20260907"}
po = EX.plan_order(sig, "20260904")
ok("计划生成", po["ok"] and po["status"] == "PENDING_ORDER", str(po))
ok("不含实际成交价", po.get("actual_filled_price") is None)
ok("valid_from 保留", po["valid_from"] == "20260907")
bad = EX.plan_order({"code": "000001", "entry_ref": 9.0, "sl": 9.5, "tp": 11.0})
ok("非法信号(sl>=entry)拒绝", not bad["ok"] and bad["reason"] == "BAD_SIGNAL", str(bad))

print("== 2. try_fill：停牌/涨跌停(板块)/valid_from 统一判定 ==")
snap_ok = {"px": 10.2, "prev": 10.0, "open": 10.1, "vol": 5000, "today": "20260907"}
f = EX.try_fill(po, snap_ok)
ok("next_open 以开盘价成交", f["filled"] and abs(f["price"] - round(10.1 * 1.001, 3)) < 1e-9, str(f))
f2 = EX.try_fill(po, {**snap_ok, "vol": 0})
ok("停牌不成交", (not f2["filled"]) and f2["why"] == "SUSPENDED", str(f2))
f3 = EX.try_fill(po, {**snap_ok, "px": 10.96, "open": 10.96})  # 主板 +9.6%
ok("主板涨停拦截", (not f3["filled"]) and f3["why"] == "LIMIT_UP", str(f3))
po300 = dict(po, code="300001")  # 创业板 20%
f4 = EX.try_fill(po300, {"px": 10.96, "prev": 10.0, "open": 10.9, "vol": 100, "today": "20260907"})
ok("创业板+9.6%可成交(板块修正)", f4["filled"], str(f4))
f5 = EX.try_fill(po, {**snap_ok, "today": "20260904"})
ok("未到 valid_from 不成交", (not f5["filled"]) and f5["why"] == "NOT_YET_VALID", str(f5))
po_retrace = dict(po, entry_mode="retrace", reference_price=9.9)
f6 = EX.try_fill(po_retrace, {"px": 9.8, "prev": 10.0, "open": 10.1, "vol": 5000, "today": "20260907"})
ok("retrace 回落至限价成交", f6["filled"] and abs(f6["price"] - round(9.9 * 1.001, 3)) < 1e-9, str(f6))

print("== 3. try_exit：判定顺序与 simulate 一致 ==")
pos = {"code": "000001", "filled_price": 10.0, "sl": 9.5, "tp1": 10.6, "tp2": 11.2,
       "filled_at": "2026-09-04 09:35:00", "tp1_hit": False}
ex1 = EX.try_exit(pos, {"px": 9.4, "today": "20260907"})
ok("① SL 优先触发", ex1["exit"] and ex1["reason"] == "SL_HIT", str(ex1))
ex2 = EX.try_exit(pos, {"px": 10.7, "today": "20260907"})
ok("② TP1 部分平+SL移保本", (not ex2["exit"]) and ex2.get("partial") == "TP1" and ex2["new_state"]["sl"] == 10.0, str(ex2))
ex3 = EX.try_exit({**pos, "tp1_hit": True, "sl": 10.0}, {"px": 9.99, "today": "20260907"})
ok("③ BE(保本止损)标签", ex3["exit"] and ex3["reason"] == "BE", str(ex3))
ex4 = EX.try_exit({**pos, "tp1_hit": True, "sl": 10.0}, {"px": 11.3, "today": "20260907"})
ok("④ TP2 全平", ex4["exit"] and ex4["reason"] == "TP2_RUNNER", str(ex4))
ex5 = EX.try_exit(pos, {"px": 10.2, "today": "20260907", "bars_since_fill": 15})
ok("⑤ 时间止损最后判定", ex5["exit"] and ex5["reason"] == "TIME_STOP", str(ex5))
ex6 = EX.try_exit(pos, {"px": 9.4, "today": "20260904"})
ok("T+1 当日买入不可卖", (not ex6["exit"]) and ex6["why"] == "T1_LOCKED", str(ex6))
# 同一快照 SL 与时间止损同时满足 → SL 优先（顺序一致）
ex7 = EX.try_exit(pos, {"px": 9.0, "today": "20260907", "bars_since_fill": 15})
ok("SL 优先于时间止损(与simulate一致)", ex7["exit"] and ex7["reason"] == "SL_HIT", str(ex7))

print("== 4. try_exit 跌停不可卖 ==")
pos688 = {**pos, "code": "688001"}
ex8 = EX.try_exit(pos688, {"px": 8.0, "prev": 10.0, "today": "20260907"})
ok("科创板跌停(-20%)不可卖", (not ex8["exit"]) and ex8["why"] == "LIMIT_DOWN_SELL", str(ex8))
ex9 = EX.try_exit(pos, {"px": 8.99, "prev": 10.0, "today": "20260907"})
ok("主板-10.1%跌停不可卖", (not ex9["exit"]) and ex9["why"] == "LIMIT_DOWN_SELL", str(ex9))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)