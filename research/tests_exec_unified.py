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

# FIX(2026-09-08, P8-1 复检): ep<sl 非法区间几何回归测试 ——
# 旧 gen_v20f 内联循环对 entry_price < stop 的交易在首根K线必获利(机械bug)。
# simulate 的 BAD_ENTRY 必须拒绝；正常区间 ep>sl 不受影响。
def test_ep_lt_sl_bad_entry():
    # ep=10, sl=10.2(高于入场): 区间几何非法(入场在止损之上)
    # 旧循环: 首根 l<=10.2 即以10.2获利退出(+2%) —— 机械获利bug
    daily = [{"t": "20260101", "o": 10.0, "h": 10.1, "l": 9.9, "c": 10.0, "v": 1000000},
             {"t": "20260102", "o": 10.05, "h": 10.3, "l": 9.8, "c": 10.1, "v": 1000000}]
    r = EX.simulate(daily, 0, 10.0, 10.2, tp1=10.4, tp2=10.6, tp3=10.8,
                    partial_tp1=0.3, stop_to_be=True, max_hold=15)
    ok("P8-1: ep<sl 非法区间→BAD_ENTRY拒绝(防机械获利)", r.get("skipped") and r.get("reason") == "BAD_ENTRY",
       f"got skipped={r.get('skipped')} reason={r.get('reason')}")

def test_ep_gt_sl_normal():
    daily = [{"t": "20260101", "o": 10.0, "h": 10.1, "l": 9.9, "c": 10.0, "v": 1000000},
             {"t": "20260102", "o": 10.05, "h": 10.3, "l": 10.0, "c": 10.2, "v": 1000000},
             {"t": "20260103", "o": 10.2, "h": 10.5, "l": 10.1, "c": 10.4, "v": 1000000}]
    r = EX.simulate(daily, 0, 10.0, 9.5, tp1=10.3, tp2=10.6, tp3=10.9,
                    partial_tp1=0.3, stop_to_be=True, max_hold=15)
    ok("P8-1: 正常区间 ep>sl 正常执行", not r.get("skipped") and r["net_pnl_pct"] > 0,
       f"got skipped={r.get('skipped')} net={r.get('net_pnl_pct')}")

test_ep_lt_sl_bad_entry()
test_ep_gt_sl_normal()

print("== 复审 P0-2: 时间因果硬断言 ==")
# ① 成交时间 >= 可交易时间(valid_from)
o1 = {"code": "000001", "entry_mode": "next_open", "reference_price": 10.0,
      "planned_sl": 9.5, "planned_tp": 11.5, "valid_from": "20260907"}
s1 = {"px": 10.2, "prev": 10.0, "open": 10.1, "vol": 1000, "today": "20260906"}
r1 = EX.try_fill(o1, s1)
ok("P0-2: today<valid_from 不成交(NOT_YET_VALID)", (not r1["filled"]) and r1["why"] == "NOT_YET_VALID", str(r1))
s1b = {"px": 10.2, "prev": 10.0, "open": 10.1, "vol": 1000, "today": "20260907"}
r1b = EX.try_fill(o1, s1b)
ok("P0-2: today>=valid_from 可成交", r1b["filled"], str(r1b))
# ② 成交价不高于涨停（买入）
s1c = {"px": 11.05, "prev": 10.0, "open": 10.1, "vol": 1000, "today": "20260907"}
r1c = EX.try_fill(o1, s1c)
ok("P0-2: 涨停不可买(LIMIT_UP)", (not r1c["filled"]) and r1c["why"] == "LIMIT_UP", str(r1c))
# ③ 退出时间 > 成交时间（T+1 锁）
pos2 = {"code": "000001", "entry_date": "20260907", "filled_price": 10.0, "sl": 9.5, "tp": 11.5, "tp1": 10.5, "tp1_hit": False, "bars_since_fill": 0, "filled_at": "2026-09-07 10:00:00"}
ex2 = EX.try_exit(pos2, {"px": 10.6, "prev": 10.0, "today": "20260907"})
ok("P0-2: T+1锁定当日不可卖", (not ex2["exit"]) and ex2["why"] == "T1_LOCKED", str(ex2))
pos2b = {"code": "000001", "entry_date": "20260904", "filled_price": 10.0, "sl": 9.5, "tp": 11.5, "tp1": 10.5, "tp1_hit": False, "bars_since_fill": 1, "filled_at": "2026-09-04 10:00:00"}
ex2b = EX.try_exit(pos2b, {"px": 10.6, "prev": 10.0, "today": "20260907"})
# T+1 解除后: px 10.6 > tp1 10.5 → TP1 部分平仓(partial)即卖出被允许; 若 exit=False 仅允许 HOLD
ok("P0-2: T+1后可卖(T1锁解除→TP1部分平)", ex2b["exit"] or ex2b.get("partial") == "TP1", str(ex2b))
# ④ 同一根K线 high/low 顺序未知 → 保守规则: SL 优先于 TP（simulate 已实现）
daily3 = [{"t": "20260101", "o": 10.0, "h": 10.0, "l": 10.0, "c": 10.0, "v": 1000000},
          {"t": "20260102", "o": 10.0, "h": 11.0, "l": 9.0, "c": 10.0, "v": 1000000}]
r3 = EX.simulate(daily3, 0, 10.0, 9.8, tp1=10.4, tp2=10.8, partial_tp1=0.3, stop_to_be=True, max_hold=15)
ok("P0-2: 同K线SL优先于TP(保守)", r3["reason"] == "SL_HIT", r3["reason"])
# ⑤ try_fill 记录 fill_rule/price_source（P1-1）
r4 = EX.try_fill({"code": "000001", "entry_mode": "retrace", "reference_price": 10.0,
                  "planned_sl": 9.5, "planned_tp": 11.5, "valid_from": "20260901"},
                 {"px": 9.9, "prev": 10.0, "open": 10.1, "vol": 1000, "today": "20260907"})
ok("P1-1: retrace 回踩成交记录 fill_rule", r4["filled"] and "LIMIT_RETRACE" in r4.get("fill_rule", "") and r4.get("price_source") == "retrace", str(r4))
r5 = EX.try_fill({"code": "000001", "entry_mode": "next_open", "reference_price": 10.0,
                  "planned_sl": 9.5, "planned_tp": 11.5, "valid_from": "20260901"},
                 {"px": 10.2, "prev": 10.0, "open": 10.1, "vol": 1000, "today": "20260907"})
ok("P1-1: next_open 开盘成交记录 fill_rule", r5["filled"] and r5.get("fill_rule") == "MARKET_T1_OPEN" and r5.get("price_source") == "open", str(r5))

print("== 复审 P1-6: MAE/MFE 从 fill bar 起算（非 signal bar）==")
# 构造: entry_idx=0 (fill bar), 后续 bar 大幅波动 —— MAE/MFE 应反映 entry 后的真实不利/有利偏移
d6 = [{"t": "20260101", "o": 10.0, "h": 10.0, "l": 10.0, "c": 10.0, "v": 1000000},  # fill bar (entry_idx=0, 以open=10买入)
      {"t": "20260102", "o": 10.1, "h": 10.5, "l": 9.9, "c": 10.2, "v": 1000000},  # 第一根持有bar: MFE=(10.5/10-1)=5%, MAE=(9.9/10-1)=-1%
      {"t": "20260103", "o": 10.2, "h": 11.0, "l": 10.1, "c": 10.8, "v": 1000000}]  # 第二根: MFE=10%
r6 = EX.simulate(d6, 0, 10.0, 9.0, tp1=10.6, tp2=10.9, partial_tp1=0.3, stop_to_be=True, max_hold=15)
ok("P1-6: MFE 从 fill 后第一根bar起算(≥5%)", r6["mfe_pct"] >= 5.0, f"mfe={r6['mfe_pct']}%")
ok("P1-6: MAE 从 fill 后第一根bar起算(≤-1%)", r6["mae_pct"] <= -1.0, f"mae={r6['mae_pct']}%")
# 信号bar的极端高低不应计入（signal bar high=10.5 若误计会让 MFE 失真, 但 simulate 从 entry_idx+1 起算）
ok("P1-6: mfe_r/mae_r 为正负符号正确", r6["mfe_r"] > 0 and r6["mae_r"] < 0, f"mfe_r={r6['mfe_r']} mae_r={r6['mae_r']}")
# 未成交订单不进入 MAE/MFE 样本：BAD_ENTRY 返回 skipped，无 mfe/mae
r7 = EX.simulate(d6, 0, 10.0, 10.2, tp1=10.6, tp2=10.9, partial_tp1=0.3, stop_to_be=True, max_hold=15)
ok("P1-6: BAD_ENTRY(ep<sl) 不入 MAE/MFE 样本", r7.get("skipped"), str(r7.get("reason")))
# 同K线 SL/TP 冲突 → SL 优先（保守, 无未来函数）
d8 = [{"t": "20260101", "o": 10.0, "h": 10.0, "l": 10.0, "c": 10.0, "v": 1000000},
      {"t": "20260102", "o": 10.0, "h": 11.5, "l": 8.5, "c": 10.0, "v": 1000000}]  # 同根: high 11.5(TP), low 8.5(SL)
r8 = EX.simulate(d8, 0, 10.0, 9.8, tp1=10.4, tp2=10.8, partial_tp1=0.3, stop_to_be=True, max_hold=15)
ok("P1-6: 同K线 SL 优先于 TP（保守规则）", r8["reason"] in ("SL_HIT", "SL_GAP"), r8["reason"])

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)