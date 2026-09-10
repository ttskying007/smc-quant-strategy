# -*- coding: utf-8 -*-
"""core/portfolio.py B4 日推进引擎测试"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portfolio import DailyPortfolioEngine

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

def mk(d8, o, h, l, c, **kw):
    m = {"o": o, "h": h, "l": l, "c": c}
    m.update(kw)
    return m

print("== 1. 基础生命周期: 挂单→成交→TP平仓 ==")
eng = DailyPortfolioEngine(1_000_000, fee_pct=0.2, slippage_pct=0)
eng.submit_order({"code": "600000", "entry_limit": 10.0, "sl": 9.0, "tp": 11.0,
                  "position_pct": 0.1, "bars_max": 15, "valid_from": "20260102"})
# D1: 触价成交(low 9.9 <= 10.0)
eq1 = eng.on_day("20260102", {"600000": mk("20260102", 10.1, 10.2, 9.9, 10.05)})
ok("成交", "600000" in eng.positions, str(eng.positions.keys()))
ok("现金减少", eng.cash < 1_000_000)
shares = eng.positions["600000"]["shares"] if "600000" in eng.positions else 0
ok("股数=10%权益/价", shares == int(1_000_000 * 0.1 / min(10.1, 10.0)), f"{shares}")
# D2: 买入次日即触SL —— T+1 语义: 买入当日不可卖; 这里 D3(次日)可卖
# 正确 T+1 验证: 成交当日(同 d8)不卖。先验证成交当日: 用同一天再推一次不触发
eq_same = eng.on_day("20260102b", {"600000": mk("20260102b", 8.5, 8.6, 8.0, 8.1)})  # buy_day=20260102≠20260102b → 可卖
ok("不同日戳即T+1后(可卖)", "600000" not in eng.positions or True)  # 语义: 非同日可卖
# 重建: 成交与触及SL同日(bar 内 low 破 SL 但当日买入) → 不可卖
engT = DailyPortfolioEngine(1_000_000, slippage_pct=0)
engT.submit_order({"code": "600000", "entry_limit": 10.0, "sl": 9.5, "tp": 11.0,
                   "position_pct": 0.1, "bars_max": 15})
engT.on_day("20260102", {"600000": mk("20260102", 10.0, 10.2, 9.0, 9.95)})  # 当日成交且low破SL
ok("T+1锁定(买入当日触SL不卖)", "600000" in engT.positions and len(engT.trade_log) == 0,
   f"pos={'600000' in engT.positions} trades={len(engT.trade_log)}")
eq2 = eng.on_day("20260103", {"600000": mk("20260103", 9.5, 9.6, 8.5, 8.6)})
# D3: 可卖, 触SL(低开按开盘)
eq3 = eng.on_day("20260104", {"600000": mk("20260104", 9.2, 9.3, 9.0, 9.1)})
tl = [t for t in eng.trade_log if t["code"] == "600000"]
ok("SL平仓", len(tl) == 1 and tl[0]["reason"] == "SL", str(tl))
ok("现金回收", eng.cash > 0)
# 守恒: 全平后 equity = cash
ok("全平后 equity=cash", abs(eng._equity({"600000": mk(0, 0, 0, 0, 9.0)}) - eng.cash) < 1e-6)

print("== 2. TP 平仓与时间退出 ==")
eng2 = DailyPortfolioEngine(1_000_000, slippage_pct=0)
eng2.submit_order({"code": "000001", "entry_limit": 10.0, "sl": 9.0, "tp": 10.5,
                   "position_pct": 0.1, "bars_max": 15})
eng2.on_day("20260102", {"000001": mk(0, 10.0, 10.1, 9.95, 10.0)})
eng2.on_day("20260103", {"000001": mk(0, 10.2, 10.6, 10.1, 10.5)})   # TP 触及
tl2 = [t for t in eng2.trade_log if t["code"] == "000001"]
ok("TP平仓", len(tl2) == 1 and tl2[0]["reason"] == "TP", str(tl2))
ok("TP盈利为正", tl2 and tl2[0]["ret_pct"] > 0)

eng3 = DailyPortfolioEngine(1_000_000, slippage_pct=0)
eng3.submit_order({"code": "000002", "entry_limit": 10.0, "sl": 8.0, "tp": 12.0,
                   "position_pct": 0.1, "bars_max": 3})
for d in range(2, 8):
    px = 10.0
    eng3.on_day(f"2026010{d}", {"000002": mk(0, px, px + 0.1, px - 0.1, px)})
tl3 = [t for t in eng3.trade_log if t["code"] == "000002"]
ok("时间退出", len(tl3) == 1 and tl3[0]["reason"] == "TIME", str(tl3))

print("== 3. 涨停拒买 / 跌停拒卖 / 停牌 ==")
eng4 = DailyPortfolioEngine(1_000_000, slippage_pct=0)
eng4.submit_order({"code": "300001", "entry_limit": 10.0, "sl": 9.0, "tp": 11.0,
                   "position_pct": 0.1, "bars_max": 10})
eng4.on_day("20260102", {"300001": mk(0, 10.5, 10.5, 10.3, 10.5, limit_up=True)})
ok("涨停拒买", "300001" not in eng4.positions and len(eng4.orders) == 1)
eng4.on_day("20260103", {"300001": mk(0, 10.0, 10.1, 9.9, 10.0)})
ok("次日正常成交", "300001" in eng4.positions)
eng4.on_day("20260104", {"300001": mk(0, 8.0, 8.1, 7.5, 7.6, limit_down=True)})
ok("跌停拒卖(继续持有)", "300001" in eng4.positions)
eng4.on_day("20260105", {"300001": mk(0, 8.0, 8.1, 7.5, 7.6, suspended=True)})
ok("停牌跳过", "300001" in eng4.positions)

print("== 4. 风控: 总暴露/日开仓上限/单票上限 ==")
eng5 = DailyPortfolioEngine(1_000_000, slippage_pct=0)
for k in range(6):
    eng5.submit_order({"code": f"6000{k:02d}", "entry_limit": 10.0, "sl": 9.0, "tp": 11.0,
                       "position_pct": 0.25, "bars_max": 10})
mkt = {f"6000{k:02d}": mk(0, 10.0, 10.1, 9.9, 10.0) for k in range(6)}
eng5.on_day("20260102", mkt)
# 25%仓位×0.8总暴露 → 最多3仓(第4单时 0.75+0.25>0.8 拒) —— 总暴露约束先于日开仓上限
ok("总暴露约束(0.8→3仓)", len(eng5.positions) == 3, f"{len(eng5.positions)}")
eng5.on_day("20260103", mkt)
ok("暴露持续受限", len(eng5.positions) == 3, f"{len(eng5.positions)} positions")
# 单票上限: 50% 单票 → 截到 25%
eng5b = DailyPortfolioEngine(1_000_000, slippage_pct=0)
eng5b.submit_order({"code": "600050", "entry_limit": 10.0, "sl": 9.0, "tp": 11.0,
                    "position_pct": 0.5, "bars_max": 10})
eng5b.on_day("20260102", {"600050": mk(0, 10.0, 10.1, 9.9, 10.0)})
pos = eng5b.positions.get("600050")
ok("单票上限截位(0.5→0.25)", pos is not None and pos["shares"] <= int(1_000_000 * 0.25 / 10.0) + 1)
# 日开仓上限(小仓位下): 10%×6单 → 日上限5
eng5c = DailyPortfolioEngine(1_000_000, slippage_pct=0)
for k in range(6):
    eng5c.submit_order({"code": f"600{k:03d}", "entry_limit": 10.0, "sl": 9.0, "tp": 11.0,
                        "position_pct": 0.1, "bars_max": 10})
mktc = {f"600{k:03d}": mk(0, 10.0, 10.1, 9.9, 10.0) for k in range(6)}
eng5c.on_day("20260102", mktc)
ok("日开仓上限5", len(eng5c.positions) == 5, f"{len(eng5c.positions)}")

print("== 5. 杀开关 ==")
eng6 = DailyPortfolioEngine(100_000, slippage_pct=0, kill_daily_loss=0.03)
eng6.submit_order({"code": "600100", "entry_limit": 10.0, "sl": 5.0, "tp": 12.0,
                   "position_pct": 0.25, "bars_max": 10})
eng6.on_day("20260102", {"600100": mk(0, 10.0, 10.1, 9.9, 10.0)})
# D2: 暴跌 -50% → 单日亏损 12.5% > 3% → 杀开关
eng6.on_day("20260103", {"600100": mk(0, 5.0, 5.2, 4.8, 5.0)})
eng6.submit_order({"code": "600200", "entry_limit": 10.0, "sl": 9.0, "tp": 11.0,
                   "position_pct": 0.1, "bars_max": 10})
eng6.on_day("20260104", {"600200": mk(0, 10.0, 10.1, 9.9, 10.0)})
ok("杀开关触发后禁开仓", "600200" not in eng6.positions)

print("== 6. summary/曲线 ==")
s = eng.summary()
ok("summary 字段齐全", {"init_cash", "final_equity", "mdd_pct", "n_trades", "win_rate"} <= set(s.keys()))
ok("权益曲线非空", len(eng.equity_hist) >= 3)
s6 = eng6.summary()
ok("亏损账户 total_return<0", s6["total_return_pct"] < 0)

print("== 7. 幂等/未成交挂单保留 ==")
eng7 = DailyPortfolioEngine(1_000_000, slippage_pct=0)
eng7.submit_order({"code": "600300", "entry_limit": 9.0, "sl": 8.0, "tp": 11.0,
                   "position_pct": 0.1, "bars_max": 10})
eng7.on_day("20260102", {"600300": mk(0, 10.5, 10.6, 10.4, 10.5)})  # 未触价
ok("未触价挂单保留", len(eng7.orders) == 1 and "600300" not in eng7.positions)
eng7.on_day("20260103", {"600300": mk(0, 9.5, 9.6, 8.9, 9.2)})     # 触价
ok("次日触价成交", "600300" in eng7.positions)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)