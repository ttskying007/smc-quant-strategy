# -*- coding: utf-8 -*-
"""core/execution.py 统一执行模块单元测试（F07）"""
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

def mk(vals):
    return [{"t": "202601%02d" % (1 + i), "o": o, "h": h, "l": l, "c": c, "v": 1000000}
            for i, (o, h, l, c) in enumerate(vals)]

print("== 1. 入场约束 ==")
# 一字涨停：prev=10, open=11.2 >= 10*1.095
daily = mk([(10, 10.2, 9.8, 10)] * 3 + [(11.2, 11.5, 11.1, 11.3)])
ok("一字涨停跳过", EX.entry_ok(daily, 3, 11.2, 9.5)[1] == "SKIP_LIMIT_UP")
ok("正常入场", EX.entry_ok(mk([(10, 10.2, 9.8, 10)] * 4), 3, 10.1, 9.5)[0])

print("== 2. SL_HIT ==")
daily = mk([(10.1, 10.3, 10.0, 10.2), (10.0, 10.1, 9.4, 9.5)])
r = EX.simulate(daily, 0, 10.1, 9.5, tp2=11.0, max_hold=3)
ok("SL_HIT 触发", r["reason"] == "SL_HIT", str(r["reason"]))
ok("SL_HIT 收益为负", r["net_pnl_pct"] < 0)

print("== 3. TP_STRUCTURAL ==")
daily = mk([(10.0, 10.2, 9.9, 10.1), (10.1, 11.2, 10.0, 11.0)])
r = EX.simulate(daily, 0, 10.0, 9.5, tp2=11.0, max_hold=3)
ok("TP_STRUCTURAL 触发", r["reason"] == "TP_STRUCTURAL", str(r["reason"]))
ok("TP 收益为正", r["net_pnl_pct"] > 0)

print("== 4. 跳空低开 SL_GAP ==")
daily = mk([(10.0, 10.2, 9.9, 10.1), (9.2, 9.3, 9.1, 9.2)])
r = EX.simulate(daily, 0, 10.0, 9.5, tp2=11.0, max_hold=3)
ok("SL_GAP 按开盘价", r["reason"] == "SL_GAP" and abs(r["exit_price"] - 9.2) < 1e-6, str(r))

print("== 5. 分批 TP1 + TP2 runner ==")
daily = mk([(10.0, 10.2, 9.9, 10.1), (10.1, 10.6, 10.0, 10.5), (10.5, 11.2, 10.4, 11.0)])
r = EX.simulate(daily, 0, 10.0, 9.0, tp1=10.6, tp2=11.2, partial_tp1=0.4, max_hold=4)
ok("TP2_RUNNER 触发", r["reason"] == "TP2_RUNNER", str(r["reason"]))

print("== 6. 时间止损 TIME_STOP ==")
daily = mk([(10.0, 10.2, 9.9, 10.1)] * 6)
r = EX.simulate(daily, 0, 10.0, 9.5, tp2=15.0, max_hold=5)
ok("TIME_STOP 触发", r["reason"] == "TIME_STOP", str(r["reason"]))
ok("hold=5", r["hold_bars"] == 5, str(r["hold_bars"]))

print("== 7. MFE/MAE 输出 ==")
r = EX.simulate(mk([(10.0, 10.2, 9.9, 10.1), (10.1, 11.2, 10.0, 11.0)]), 0, 10.0, 9.5, tp2=11.0, max_hold=3)
ok("mfe_pct>0", r["mfe_pct"] > 0, str(r["mfe_pct"]))
ok("mfe_r 计算", r["mfe_r"] > 0, str(r["mfe_r"]))

print("== 8. 涨跌停/停牌判定 ==")
ok("涨停拦截买入", EX.is_limit_up({"px": 11.0, "prev": 10.0}, "buy"))
ok("跌停拦截卖出", EX.is_limit_up({"px": 9.0, "prev": 10.0}, "sell"))
ok("停牌(量0)", EX.is_suspended({"px": 10.0, "prev": 10.0, "vol": 0}))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
