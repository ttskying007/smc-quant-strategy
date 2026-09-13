# -*- coding: utf-8 -*-
"""交易日历模块测试（第七轮审计 P1 清单#3）: 真实交易日 TTL 替代自然日近似。
数据源: 腾讯个股日线缓存聚合(800 交易日, 覆盖 2023-05..2026-09-11)。"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import trading_calendar as TC

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + detail)

print("== 1. 基础日历属性 ==")
TC._load()
ok("日历规模 700-900 (聚合有效, 非纯周末)", 700 <= len(TC._CAL) <= 900, f"n={len(TC._CAL)}")
ok("最新=20260911 (缓存末日)", TC._LATEST == "20260911", TC._LATEST)
# 周末必非交易日(抽 2026 全年周六)
_sat = [d for d in TC._CAL if d[:6] == "202609" and __import__("datetime").date(2026, 9, int(d[6:8])).weekday() == 5]
ok("2026-09 无周六交易日", len(_sat) == 0, str(_sat[:3]))

print("== 2. 节假日(数据驱动, 非周末) ==")
# 2024 春节休市 2/9-2/18; 2024 清明 4/4-4/6; 2025 春节 1/28-2/4
for d, name in [("20240212", "2024春节(周一2/12)"), ("20240404", "2024清明(周四)"),
                ("20250130", "2025春节(周四1/30)"), ("20250203", "2025春节(周一2/3)")]:
    ok(f"{name} 休市", d not in TC._CAL, "误判为交易日")
ok("2024春节后首日 20240219 开市", "20240219" in TC._CAL)
ok("2024春节前最后交易日 20240208", "20240208" in TC._CAL and TC.next_td("20240208") == "20240219",
   f"next={TC.next_td('20240208')}")

print("== 3. 接口语义 ==")
ok("next_td 跨周末(周五→周一)", TC.next_td("20260911") == "20260914")
ok("next_td 缓存末日后前向外推(周一工作日)", TC.next_td("20260911") == "20260914")
ok("prev_td(周一→上周五)", TC.prev_td("20260914") == "20260911")
ok("add_td_days(周五,+3)=下周三", TC.add_td_days("20260911", 3) == "20260916")
ok("add_td_days(0,当日为交易日)", TC.add_td_days("20260911", 0) == "20260911")
ok("add_td_days 跨春节(2/8 +1 = 2/19)", TC.add_td_days("20240208", 1) == "20240219")
ok("td_between 闭区间含端点", TC.td_between("20260907", "20260911") == 5)
ok("td_between 休市区间=0", TC.td_between("20240209", "20240218") == 0)
ok("td_between 无序自动交换", TC.td_between("20260911", "20260907") == TC.td_between("20260907", "20260911"))
ok("is_td 一致性", TC.is_td("20260911") and not TC.is_td("20260912"))

print("== 4. PENDING TTL 生产语义(替代自然日×2近似) ==")
# 场景: valid_from=周五 09-11, PENDING_EXPIRE_DAYS=3
# 自然日近似: 周一(3 自然日>6? 否)→ 周四(3×2=6 自然日) 过期 —— 周末占2天, 实际只3交易日
# 交易日: 周一(td=2) 周二(3) 周三(4>3) → EXPIRED 于周三
_n_fri_to_wed = TC.td_between("20260911", "20260916")
ok("周五挂单到下周三=4个交易日(>3 触发EXPIRED)", _n_fri_to_wed == 4, str(_n_fri_to_wed))
_n_fri_to_tue = TC.td_between("20260911", "20260915")
ok("周五挂单到下周二=3个交易日(=3 不触发)", _n_fri_to_tue == 3, str(_n_fri_to_tue))
# 春节场景: valid_from=2024-02-08(节前最后日), 3 交易日 TTL
# 真实: 2/19(td=2) 2/20(td=3) 2/21(td=4>3) → EXPIRED 于 2/21
# 自然日×2 近似: 2/8+6 自然日=2/14(仍休市) → 要等到 2/19 才能比对, 行为偏晚且语义错
_n_cny = TC.td_between("20240208", "20240221")
ok("春节挂单(2/8)到2/21=4个交易日(>3 触发)", _n_cny == 4, str(_n_cny))
_n_cny2 = TC.td_between("20240208", "20240220")
ok("春节挂单(2/8)到2/20=3个交易日(=3 不触发)", _n_cny2 == 3, str(_n_cny2))

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)