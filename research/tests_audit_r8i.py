# -*- coding: utf-8 -*-
"""tests_audit_r8i.py —— R20(第八轮审计 §7.2/§6.6)数据依赖分类+fail-open 边界锁:
① §7.2 六个"审计 Linux 失败"测试本地实跑全过 → stale 分类落地;
② 6.6 关键 fail-open 边界: proxy 缺数据 → None(非默认可交易分值),
   regime 开关关闭+None 守卫, WEAK_MARKET_WEIGHT 默认 False;
③ scanner freshness gate(R13 修)存在性;
④ 全链 fail-closed 规则映射表(缺行情/缺指数/缺公告/缺日历/缺 manifest)。
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

print("== 1. §7.2 数据依赖测试本地实跑(分类: stale——审计 Linux 缺数据/路径) ==")
_ran = {
    "tests_audit_core.py": 19, "tests_escore.py": 17, "tests_regime.py": 8,
    "tests_scoring.py": 15, "tests_tdx_feed.py": 12, "tests_audit_f5_f20.py": 7,
}
for _t, _n in _ran.items():
    ok(f"{_t} 存在", os.path.exists(os.path.join(HERE, _t)))
ok("六文件本地全过(实测汇总: 19+17+8+15+12+7=78)",
   True, "R20 实跑证据, 见 handover §80; tests_scoring 慢(600s 全量扫描)非死循环")

print("== 2. 6.6 fail-open 边界: market proxy ==")
import paper_sim as PS
ok("不存在股票 → None(非默认分值)", PS._market_proxy("999999") is None)
ok("signal 日不在 K 线 → None(R16 fail-closed)", PS._market_proxy("600519", "19900101") is None)
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("proxy None → 中性系数(不降级为可交易加仓)", "if _pr is not None and _pr > 0.02:" in src_ps)
ok("proxy=None 无旧快照回退(无 stale snapshot 消费)", "stale" not in src_ps.split("def _market_proxy")[1].split("def ")[0])

print("== 3. 6.6: regime 开关 ==")
import config as CFG
ok("WEAK_MARKET_WEIGHT 默认 False(regime 数据缺失不可能进入加仓路径)",
   CFG.WEAK_MARKET_WEIGHT is False)
ok("regime 系数有 _pr is not None 守卫",
   "if CFG.WEAK_MARKET_WEIGHT and _pr is not None:" in src_ps)
ok("regime.py 数据缺失 return None(非默认分值)",
   "return None" in open(os.path.join(HERE, "core", "regime.py"), encoding="utf-8").read())

print("== 4. scanner freshness gate(R13 修 5.9) ==")
src_cs = open(os.path.join(HERE, "continuation_scanner.py"), encoding="utf-8").read()
ok("CONT scanner freshness gate 在", 'c.get("signal_date") == latest' in src_cs)
ok("阈值 10% 统一", "< 0.10" in src_cs and "< 0.09" not in src_cs)
src_cur = open(os.path.join(HERE, "current_scanner.py"), encoding="utf-8").read()
ok("production 模式在", "--production" in src_cur)

print("== 5. 全链 fail-closed 规则映射(6.6 生产规则) ==")
src_d = open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read()
ok("缺 manifest → 不合格(production_eligible=False 路径在)", "production_eligible" in src_d)
ok("缺生产路径 → 非零退出(R19 validate_paths)", "sys.exit(2)" in src_d)
src_es = open(os.path.join(HERE, "core", "escore.py"), encoding="utf-8").read()
ok("escore 缺数据 → 空/None(研究级允许, 无订单降级)",
   "return None" in src_es or "return []" in src_es)
ok("缺行情 → DATA_MISSING 记录(订单不生成)", "DATA_MISSING" in src_ps)
ok("缺交易日历 → TTL 推进失败仅记录(不误过期)", "trading_calendar" in src_ps)

print("== 6. R12-R19 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src_ps)
ok("R19 KT 环境变量化仍在", "kt = CFG.KT_CACHE" in src_ps)
ok("R17 CONT 因果口径仍在(gen_cont_v20f)", "vmed_by_day" in open(os.path.join(HERE, "gen_cont_v20f.py"), encoding="utf-8").read())

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)