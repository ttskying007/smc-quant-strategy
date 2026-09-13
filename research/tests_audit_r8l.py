# -*- coding: utf-8 -*-
"""tests_audit_r8l.py —— R23(第八轮审计 P1-8/P1-11/P1-12)三项回归锁:
① P1-8: gen_v20f max_hold=15 vs 生产 12 分叉显式标注(冻结基线保护);
② P1-11: _next_td 交易日历优先(节假日对齐, 周末公告跳周一);
③ P1-12: limit_pct_for docstring 诚实化(ST 判定不在本层, 保守偏差标注)。
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

print("== 1. P1-8: max_hold 分叉标注 ==")
src_g = open(os.path.join(HERE, "gen_v20f.py"), encoding="utf-8").read()
ok("max_hold=15 分叉标注在", "持有期分叉标注(R23, 第八轮审计 P1-8)" in src_g)
ok("15 vs 12 差异写明", "15 vs 12" in src_g)
ok("冻结基线保护说明在", "n=1639±1" in src_g)
ok("不得直接作为生产证据在", "不得直接作为生产事件腿证据" in src_g)
ok("重基线路径写明(与 P1-7 同批)", "与 P1-7 ADX 分叉同批处理" in src_g)

print("== 2. P1-11: _next_td 交易日历优先 ==")
import paper_sim as PS
from core.trading_calendar import next_td, is_td
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("非交易日公告 → 日历 next_td 优先", "from core.trading_calendar import next_td" in src_ps)
ok("最后交易日推下一日 → 日历优先", "节假日对齐" in src_ps)
# 行为验证(真实数据): 周末公告跳周一
bs = PS.bars_of("600519")
dates = [b["t"] for b in bs]
_r_sat = PS._next_td(dates, "20260912")  # 周六公告
_r_sun = PS._next_td(dates, "20260913")  # 周日公告
_r_latest = PS._next_td(dates, "20260911")  # 最新交易日
ok("周六公告 → 周一 20260914", _r_sat == "20260914", _r_sat)
ok("周日公告 → 周一 20260914", _r_sun == "20260914", _r_sun)
ok("最新交易日 → 下一交易日(不返回自身)", _r_latest == "20260914", _r_latest)
# 日历已知行为
ok("is_td 交易日=True", is_td("20260911") is True)
ok("is_td 周末=False", is_td("20260912") is False)

print("== 3. P1-12: limit_pct_for 诚实化 ==")
from core.execution import limit_pct_for
src_ex = open(os.path.join(HERE, "core", "execution.py"), encoding="utf-8").read()
ok("ST 判定不在本层声明", "不含 ST 判定" in src_ex)
ok("保守偏差方向标注", "保守" in src_ex and "偏差" in src_ex)
ok("调用方需自行 ST 判定说明", "调用方" in src_ex)
ok("旧歧义表述已删(规则行不再含'此处按代码')",
   "北交所(4/8/9开头,BJ) 30% | ST 5%" not in src_ex)
# 行为: 板块规则保持
ok("主板 10%", limit_pct_for("600000") == 0.10)
ok("创业板 20%", limit_pct_for("300001") == 0.20)
ok("科创板 20%", limit_pct_for("688001") == 0.20)
ok("北交所 30%", limit_pct_for("830001") == 0.30)

print("== 4. R12-R22 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src_ps)
ok("ADX 单源入口仍在", "from core.indicators import adx14_of as _adx_core" in src_ps)
ok("时区单源仍在", "from core.time_cn import cn_now, cn_today" in src_ps)
ok("R19 KT 环境变量化仍在", "kt = CFG.KT_CACHE" in src_ps)
ok("R17 CONT 因果口径仍在", "vmed_by_day" in open(os.path.join(HERE, "gen_cont_v20f.py"), encoding="utf-8").read())

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)