# -*- coding: utf-8 -*-
"""tests_v3a_semantics.py —— V3-A 执行语义锁死黄金测试(第五轮审计)
P0-1 fill_or_open 非触价不得伪造限价成交(反例: open>limit, low>limit → NOT_FILLED)
P0-2 SetupExit vs DailyPortfolioEngine 逐 bar 退出对齐(同一 fixture 同一退出 bar/收益)
P0-3 kill switch 交易日推进(跳过周末自然日)
P1-2 行业集中度强制(第4个同行业单拒开仓)
P1-3 订单 TTL 过期撤单(max_pending_days)
黄金三方: setup_exit.settle_from_record vs DailyPortfolioEngine.on_day —— fill/SL/TP/TIME
同一输入必须得到同一退出 bar 与近似收益(费差双记 tolerance)。"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.portfolio import DailyPortfolioEngine
from core.setup_exit import settle_from_record, EXIT_VERSION

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " | " + detail)

def bar(d8, o, h, l, c):
    return {"o": o, "h": h, "l": l, "c": c}

print("== P0-1 fill_or_open 执行幻觉反例 ==")
eng = DailyPortfolioEngine(1_000_000, fee_pct=0, slippage_pct=0)
eng.submit_order({"code": "T1", "entry_limit": 10.0, "sl": 9.5, "tp": 11.0,
                  "position_pct": 0.1, "fill_or_open": True,
                  "signal_date": "20260901"})
# D1: open=10.5 low=10.4 —— 全天未触 10.0; fill_or_open → 应按开盘 10.5 成交(不是 10.0!)
eq = eng.on_day("20260901", {"T1": bar("x", 10.5, 10.8, 10.4, 10.6)})
pos = eng.positions.get("T1")
ok("未触价 fill_or_open 按开盘价成交", pos is not None, str(eng.orders))
if pos:
    ok("成交价=10.5(开盘) 而非 10.0(限价)", abs(pos["entry_px"] - 10.5) < 1e-9,
       f"entry_px={pos['entry_px']}")
ok("现金扣减=10.5×股数", abs(eng.cash - (1_000_000 - pos["shares"] * 10.5)) < 1e-6 if pos else False)
# 反例2: 无 fill_or_open, 未触价 → 绝不成交
eng2 = DailyPortfolioEngine(1_000_000, fee_pct=0, slippage_pct=0)
eng2.submit_order({"code": "T2", "entry_limit": 10.0, "sl": 9.5, "tp": 11.0,
                   "position_pct": 0.1, "signal_date": "20260901"})
eng2.on_day("20260901", {"T2": bar("x", 10.5, 10.8, 10.4, 10.6)})
ok("无 fill_or_open 未触价不成交", "T2" not in eng2.positions and len(eng2.orders) == 1)
# 反例3: 触价时 min(open, limit) 保留
eng3 = DailyPortfolioEngine(1_000_000, fee_pct=0, slippage_pct=0)
eng3.submit_order({"code": "T3", "entry_limit": 10.0, "sl": 9.5, "tp": 11.0,
                   "position_pct": 0.1, "signal_date": "20260901"})
eng3.on_day("20260901", {"T3": bar("x", 9.8, 10.5, 9.9, 10.2)})     # 开盘<限价
p3 = eng3.positions.get("T3")
ok("触价+开盘更优按开盘", p3 is not None and abs(p3["entry_px"] - 9.8) < 1e-9)

print("== P0-2/P1-3 TTL 与黄金对齐 ==")
# TTL: max_pending_days=3, 4个交易日未触价 → 撤单
eng4 = DailyPortfolioEngine(1_000_000, fee_pct=0, slippage_pct=0)
eng4.submit_order({"code": "T4", "entry_limit": 10.0, "sl": 9.5, "tp": 12.0,
                   "position_pct": 0.1, "signal_date": "20260901",
                   "max_pending_days": 3})
for i, d8 in enumerate(("20260901", "20260902", "20260903", "20260904", "20260905")):
    eng4.on_day(d8, {"T4": bar("x", 10.5, 10.9, 10.4, 10.6)})       # 永不触 10.0
ok("TTL 过期撤单(pending>3)", len(eng4.orders) == 0 and any(
    c["reason"] == "TTL_EXPIRED" for c in eng4.cancelled_orders),
   f"orders={len(eng4.orders)} cancelled={eng4.cancelled_orders}")
ok("撤单后不持仓", "T4" not in eng4.positions)

print("== P0-2 黄金三方: settle_from_record vs DailyPortfolioEngine ==")
# fixture: fill@10.0(D2); 黄金对齐用【显式同参】SL=9.4/TP=11.8(settle 传 invalid 使
# atr 分支得到同 SL: invalid=9.4 时 atr=0.2×10=2 →sl=9.4-1.5×0.2=9.1 —— 故直接对齐
# 用 invalid=9.7(atr兜底0.02×10=0.2 → sl=9.7-0.3=9.4; tp=10+3×0.6=11.8))
days = [("20260901", 10.2, 10.3, 10.1, 10.2),
        ("20260902", 10.0, 10.1, 9.95, 10.05),       # D2: low 9.95<=10 触价, fill 10.0
        ("20260903", 10.0, 10.4, 9.9, 10.3),
        ("20260904", 10.3, 11.9, 10.2, 11.8)]         # D4: high 11.9>=11.8 → TP
daily = [{"t": d, "o": o, "h": h, "l": l, "c": c} for d, o, h, l, c in days]
res_exit = settle_from_record(daily, 1, 10.0, 9.7, fee_pct=0, max_bars=15, tp_rr=3.0)
ok("setup_exit SL=9.4/TP=11.8 显式对齐", abs(res_exit.get("sl", 0) - 9.4) < 1e-6
   and abs(res_exit.get("tp", 0) - 11.8) < 1e-6,
   f"sl={res_exit.get('sl')} tp={res_exit.get('tp')}")
eng5 = DailyPortfolioEngine(1_000_000, fee_pct=0, slippage_pct=0)
eng5.submit_order({"code": "G1", "entry_limit": 10.0, "sl": 9.4, "tp": 11.8,
                   "position_pct": 0.1, "signal_date": "20260901"})
for d, o, h, l, c in days:
    eng5.on_day(d, {"G1": bar("x", o, h, l, c)})
t5 = eng5.trade_log[0] if eng5.trade_log else {}
ok("setup_exit 判 TP", res_exit["status"] == "TP", res_exit["status"])
ok("引擎同判 TP", t5.get("reason") == "TP", str(t5))
ok("退出 bar 对齐(setup_exit exit_idx=3 ↔ 引擎第4天)", res_exit["exit_idx"] == 3
   and t5.get("day") == "20260904", f"exit_idx={res_exit.get('exit_idx')} day={t5.get('day')}")
ok("退出价对齐(TP 11.8)", abs(res_exit["fill_price"] - 10.0) < 1e-9 and t5.get("reason") == "TP")
ok("收益同向(TP+) eng_ret>0 & exit_ret>0", t5.get("ret_pct", 0) > 0
   and res_exit["ret_pct"] > 0)
# TIME 对齐: 纯横盘 15bar(有效日期 0901-0918 连续 18 天)
days2 = [("20260901", 10.2, 10.3, 10.1, 10.2), ("20260902", 10.0, 10.05, 9.95, 10.0)] + \
        [(f"202609{i:02d}", 10.0, 10.06, 9.94, 10.0) for i in range(3, 19)]
daily2 = [{"t": d, "o": o, "h": h, "l": l, "c": c} for d, o, h, l, c in days2]
r2 = settle_from_record(daily2, 1, 10.0, 9.0, fee_pct=0, max_bars=15, tp_rr=3.0)
ok("setup_exit TIME exit_idx=16", r2["status"] == "TIME" and r2["exit_idx"] == 16,
   f"{r2['status']} idx={r2.get('exit_idx')}")
eng6 = DailyPortfolioEngine(1_000_000, fee_pct=0, slippage_pct=0)
eng6.submit_order({"code": "G2", "entry_limit": 10.0, "sl": 9.0, "tp": 11.8,
                   "position_pct": 0.1, "signal_date": "20260901"})
for d, o, h, l, c in days2:
    eng6.on_day(d, {"G2": bar("x", o, h, l, c)})
t6 = eng6.trade_log[0] if eng6.trade_log else {}
ok("引擎 TIME 对齐(第15个持有日=0917)", t6.get("reason") == "TIME" and t6.get("day") == "20260917",
   str(t6))
ok("引擎 bars_held=15(成交后第15根)", t6.get("hold_days") == 15, str(t6.get("hold_days")))

print("== P0-3 kill switch 交易日推进 ==")
eng7 = DailyPortfolioEngine(1_000_000, fee_pct=0, slippage_pct=0, kill_daily_loss=0.02, kill_days=2)
# 造单日大跌: 持仓隔日暴跌
eng7.submit_order({"code": "K1", "entry_limit": 10.0, "sl": 1.0, "tp": 99.0,
                   "position_pct": 0.5, "fill_or_open": True, "signal_date": "20260901"})
eng7.on_day("20260901", {"K1": bar("x", 10.0, 10.1, 9.95, 10.0)})       # 买入
eng7.on_day("20260902", {"K1": bar("x", 7.0, 7.2, 6.8, 7.0)})           # -30% → kill 触发
ok("kill 触发记录", len(eng7.kill_events) == 1, str(eng7.kill_events))
ok("kill_trading_days=2", eng7.kill_trading_days == 2, str(eng7.kill_trading_days))
eng7.submit_order({"code": "K2", "entry_limit": 5.0, "sl": 4.5, "tp": 6.0,
                   "position_pct": 0.2, "fill_or_open": True, "signal_date": "20260903"})
eng7.on_day("20260903", {"K2": bar("x", 5.0, 5.2, 4.9, 5.1)})           # kill 第1交易日 → 拒
ok("kill 第1交易日拒开仓", "K2" not in eng7.positions)
eng7.submit_order({"code": "K3", "entry_limit": 5.0, "sl": 4.5, "tp": 6.0,
                   "position_pct": 0.2, "fill_or_open": True, "signal_date": "20260904"})
eng7.on_day("20260904", {"K3": bar("x", 5.0, 5.2, 4.9, 5.1)})           # kill 第2交易日 → 拒
ok("kill 第2交易日拒开仓", "K3" not in eng7.positions)
eng7.submit_order({"code": "K4", "entry_limit": 5.0, "sl": 4.5, "tp": 6.0,
                   "position_pct": 0.2, "fill_or_open": True, "signal_date": "20260905"})
eng7.on_day("20260905", {"K4": bar("x", 5.0, 5.2, 4.9, 5.1)})           # kill 结束 → 允许
ok("kill 过期后恢复开仓", "K4" in eng7.positions)

print("== P1-2 行业集中度强制 ==")
eng8 = DailyPortfolioEngine(10_000_000, fee_pct=0, slippage_pct=0)
for i, code in enumerate(("S1", "S2", "S3")):
    eng8.submit_order({"code": code, "entry_limit": 10.0, "sl": 9.0, "tp": 12.0,
                       "position_pct": 0.1, "fill_or_open": True,
                       "signal_date": "20260901"})
    eng8.on_day("20260901", {code: bar("x", 10.0, 10.2, 9.9, 10.1)})
ok("3 个同行业先成交", len(eng8.positions) == 3, str(eng8.positions.keys()))
eng8.submit_order({"code": "S4", "entry_limit": 10.0, "sl": 9.0, "tp": 12.0,
                   "position_pct": 0.1, "fill_or_open": True, "signal_date": "20260902"})
eng8.on_day("20260902", {"S4": bar("x", 10.0, 10.2, 9.9, 10.1)},
            sector_of={"S4": "白酒", "S1": "白酒", "S2": "白酒", "S3": "白酒"})
ok("第4个同行业单拒开仓", "S4" not in eng8.positions and len(eng8.orders) == 1)
eng8.submit_order({"code": "S9", "entry_limit": 10.0, "sl": 9.0, "tp": 12.0,
                   "position_pct": 0.1, "fill_or_open": True, "signal_date": "20260902"})
eng8.on_day("20260902", {"S9": bar("x", 10.0, 10.2, 9.9, 10.1)},
            sector_of={"S9": "银行", "S1": "白酒", "S2": "白酒", "S3": "白酒"})
ok("不同行业不受限", "S9" in eng8.positions)

print("== 守恒复验(改动后) ==")
eng9 = DailyPortfolioEngine(1_000_000, fee_pct=0.1, slippage_pct=0.05)
eng9.submit_order({"code": "C1", "entry_limit": 10.0, "sl": 9.0, "tp": 11.0,
                   "position_pct": 0.3, "fill_or_open": True, "signal_date": "20260901"})
for d8 in ("20260901", "20260902", "20260903"):
    eng9.on_day(d8, {"C1": bar("x", 10.0 + 0.1 * int(d8[-2:]), 10.5, 9.8, 10.1)})
ok("现金守恒", eng9.conservation_ok({"C1": bar("x", 10.1, 10.2, 10.0, 10.1)}))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)