# -*- coding: utf-8 -*-
"""tests_audit_r8j.py —— R21(第八轮审计 P1-11+6.4)时区单源+Setup Engine 定位回归锁:
① core/time_cn 上海时区模块(shanghai_now/cn_now/cn_today/降级);
② paper_sim 生产时间戳全量时区感知(残留 strftime=0);
③ setup_engine_paper 研究旁路定位声明(6.4);
④ 旁路事实(独立台账, 不写 paper_ledger.json)。
"""
import os, sys, time
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. core/time_cn 模块 ==")
from core.time_cn import shanghai_now, cn_now, cn_today, tz_source
ok("模块存在且可导入", True)
ok("时区来源= zoneinfo", tz_source() == "zoneinfo:Asia/Shanghai", tz_source())
_n = shanghai_now()
ok("shanghai_now tz-aware + Asia/Shanghai", _n.tzinfo is not None and
   str(_n.tzinfo) in ("Asia/Shanghai", "Shanghai"), str(_n.tzinfo))
# 与真实上海时间比对(UTC+8 无 DST)
_utc_now = datetime.now(timezone.utc)
_sh_expect = _utc_now.astimezone(timezone(timedelta(hours=8)))
_delta = abs((_n.replace(tzinfo=None) - _sh_expect.replace(tzinfo=None)).total_seconds())
ok("shanghai_now ≈ UTC+8 当前(±120s)", _delta < 120, f"delta={_delta:.0f}s")
ok("cn_today 格式 YYYYMMDD", len(cn_today()) == 8 and cn_today().isdigit(), cn_today())
ok("cn_now 默认格式", len(cn_now()) == 19, cn_now())
ok("cn_now/cn_today 同日一致", cn_now("%Y%m%d") == cn_today())

print("== 2. paper_sim 生产时间戳时区感知 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("导入 core.time_cn 单源", "from core.time_cn import cn_now, cn_today" in src_ps)
_n_strftime = src_ps.count("time.strftime")
ok("残留 time.strftime = 0(全量 24 处已换)", _n_strftime == 0, f"残留 {_n_strftime}")
ok("cn_now 调用在(挂单/成交/日志)", src_ps.count("cn_now(") >= 20, src_ps.count("cn_now("))
ok("cn_today 调用在(撮合当日/日开仓)", src_ps.count("cn_today()") >= 3, src_ps.count("cn_today()"))

print("== 3. setup_engine_paper 研究旁路定位(6.4) ==")
src_sp = open(os.path.join(HERE, "setup_engine_paper.py"), encoding="utf-8").read()
ok("定位声明在(研究旁路)", "研究旁路(research bypass)" in src_sp)
ok("声明: 不写 paper_ledger.json", "本脚本不写 paper_ledger.json" in src_sp)
ok("声明: 生产源是 paper_sim.daily_selection", "paper_sim.daily_selection()" in src_sp)
ok("声明: 未来切主源需先 6.1 重构", "6.1 run transaction 重构" in src_sp)
ok("SAMPLED_PAPER 标注保持", '"ledger_type": "SAMPLED_PAPER"' in src_sp)

print("== 4. 旁路事实核实 ==")
ok("研究台账路径独立(handover/setup_engine_paper_ledger.json, 非生产 paper_ledger.json)",
   "setup_engine_paper_ledger.json" in src_sp and
   'os.path.join(HERE, "paper_ledger.json")' not in src_sp and
   'CFG.LEDGER' not in src_sp)
_led = os.path.join(HERE, "handover", "setup_engine_paper_ledger.json")
ok("研究台账存在(独立文件)", os.path.exists(_led))
import json as _json
if os.path.exists(_led):
    _d = _json.load(open(_led, encoding="utf-8"))
    ok("台账结构=signals/days/summary(研究统计, 非订单账本)",
       set(_d.keys()) == {"signals", "days", "summary"}, list(_d.keys())[:6])
    ok("新记录写 ledger_type=SAMPLED_PAPER(源码字段)",
       '"ledger_type": "SAMPLED_PAPER"' in src_sp)

print("== 5. R12-R20 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src_ps)
ok("R19 KT 环境变量化仍在", "kt = CFG.KT_CACHE" in src_ps)
ok("_market_proxy(code, d8) 仍在", "def _market_proxy(code, d8=None)" in src_ps)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)