# -*- coding: utf-8 -*-
"""因果时序单元测试（审计 P0-2 / P0-3 / P1-1）
覆盖：
  1. _next_td：signal 日之后首个交易日映射（含周末/盘后）
  2. daily_selection 不再要求 T+1 K 线存在（今日披露也生成挂单）
  3. continuation_scanner 信号只用 signal 日及之前数据，不用 entry 日 open/close/volume
  4. 事件分类不误杀含"公告"的真实标题（审计 P0-1 回归）
"""
import io, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paper_sim as PS
import core.events as EV
from core.execution import entry_ok

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + detail)

print("== 1. _next_td 交易日前移（P0-2 周末/盘后映射） ==")
dates = ["20260901", "20260902", "20260903", "20260904", "20260907", "20260908"]  # 周三..周五, 周一,周二
ok("周五→下周一", PS._next_td(dates, "20260904") == "20260907", PS._next_td(dates, "20260904"))
ok("周四→周五", PS._next_td(dates, "20260903") == "20260904", PS._next_td(dates, "20260903"))
ok("非交易日(sat)→下周一", PS._next_td(dates, "20260905") == "20260907", PS._next_td(dates, "20260905"))
ok("最后交易日(周二)→下周三(日历)", PS._next_td(dates, "20260908") == "20260909", PS._next_td(dates, "20260908"))
# 今日(周五)刚披露、明日无K线 → 退化为下周一(周末日历)
ok("周五披露(最后K线)→下周一", PS._next_td(dates, "20260904") == "20260907", PS._next_td(dates, "20260904"))

print("== 2. daily_selection 今日披露不再跳过（P0-2） ==")
src = open(os.path.join(os.path.dirname(PS.__file__), "paper_sim.py"), encoding="utf-8").read()
ok("已移除 `entry_idx>=len(bs) -> continue` 跳过", "if entry_idx >= len(bs):\n                continue" not in src)
ok("TP/SL 基于披露日收盘(close_px)计算", "tp4 is None or tp4 <= close_px" in src)
ok("v_ratio 用披露日量 bs[i][\"v\"]（决策时点可得）", 'v_ratio = round(bs[i]["v"] / avg_v, 2) if avg_v else 1.0' in src)
ok("valid_from 由 _next_td 计算（非写死历史T+1）", '"valid_from": _next_td(dates, d8)' in src)

print("== 3. continuation_scanner 不用未来 entry 数据（P0-3） ==")
csrc = open(os.path.join(os.path.dirname(PS.__file__), "continuation_scanner.py"), encoding="utf-8").read()
ok("signal 在最新收盘日(len-1)", "i = len(daily) - 1" in csrc)
ok("VWAP 只算到 signal 日(i)，不含 entry 日", "for k in range(i - 19, i + 1)" in csrc)
ok("entry 写为明日(valid_from)，不写历史 entry 价", '"entry_mode": "next_open"' in csrc)
ok("不引用 entry_idx 的 open/close/volume", "daily[entry_idx]" not in csrc and "range(entry_idx" not in csrc)

print("== 4. 事件分类不误杀含\"公告\"标题（P0-1 回归） ==")
ok("NEG_WORDS 不含\"公告\"", "公告" not in EV.NEG_WORDS)
is_ev, kind, pol, _, _ = EV.classify_title("关于以集中竞价交易方式回购公司A股股份方案的公告")
ok("回购...公告 → 事件", is_ev and kind == "BUYBACK" and pol > 0, f"is_ev={is_ev}")
is_ev, kind, pol, _, _ = EV.classify_title("关于控股股东增持公司股份计划的公告")
ok("增持...公告 → 事件", is_ev and kind == "HOLDER_INCREASE" and pol > 0, f"is_ev={is_ev}")
is_ev, kind, pol, _, _ = EV.classify_title("关于终止增持计划的公告")
ok("终止 → 非事件", (not is_ev) and pol <= 0, f"is_ev={is_ev} pol={pol}")
is_ev, kind, pol, _, _ = EV.classify_title("关于控股股东减持公司股份的公告")
ok("减持 → 非事件(反向)", (not is_ev) and pol < 0, f"is_ev={is_ev} pol={pol}")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)