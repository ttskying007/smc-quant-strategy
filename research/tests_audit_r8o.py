# -*- coding: utf-8 -*-
"""tests_audit_r8o.py —— R26 事故复盘回归锁(2026-09-14):
① 事故记录与回滚: 000157/002203 旧进程午夜回溯成交 → 回滚 PENDING(账本
   状态+事故note+rollback_ts) + trade_log voided;
② sim_scheduler 代码版本守卫: 7 模块 mtime 基准/变化检测三态/退出语义;
③ sim_scheduler 时区补齐(time.strftime → cn_now, R21 遗漏)。
事故根因: 09-11 19:03 启动的 --loop 进程载 09-11 代码, 09-14 00:00:09 用
周五旧 open 回溯成交(内存无 R8 几何守卫[fill 6.597>=sl 6.515 未拦截]/
R24 开盘窗口守卫[00:00 非窗口]/R15 gate)。
"""
import os, sys, json, time as _t
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. 事故回滚: 账本状态 ==")
led = json.load(open(os.path.join(HERE, "paper_ledger.json"), encoding="utf-8"))
_157 = next((t for t in led if t.get("code") == "000157" and t.get("valid_from") == "20260914"), None)
_203 = next((t for t in led if t.get("code") == "002203" and t.get("valid_from") == "20260914"), None)
ok("000157 回滚为 PENDING_ORDER", _157 and _157["status"] == "PENDING_ORDER", _157 and _157["status"])
ok("002203 回滚为 PENDING_ORDER", _203 and _203["status"] == "PENDING_ORDER", _203 and _203["status"])
ok("000157 事故 note 在", _157 and "R26事故回滚" in (_157.get("note") or ""))
ok("002203 事故 note 在", _203 and "R26事故回滚" in (_203.get("note") or ""))
ok("rollback_ts 在(两单)", _157 and _203 and _157.get("rollback_ts") and _203.get("rollback_ts"))
ok("filled_price 清空(两单)", _157 and _203 and not _157.get("filled_price") and not _203.get("filled_price"))
ok("_trade_logged_buy 复位(两单)", _157 and _203 and not _157.get("_trade_logged_buy")
   and not _203.get("_trade_logged_buy"))
ok("valid_from 保持 20260914(正常 T+1 语义)", _157 and _157.get("valid_from") == "20260914")

print("== 2. trade_log 作废标记 ==")
tl = json.load(open(os.path.join(HERE, "trade_log.json"), encoding="utf-8"))
if isinstance(tl, dict):
    tl = tl.get("trades") or tl.get("log") or []
_v = [e for e in tl if e.get("code") in ("000157", "002203") and str(e.get("ts", "")).startswith("2026-09-14 00:00")]
ok("两笔事故 BUY 已 voided", len(_v) == 2 and all(e.get("voided") for e in _v),
   [(e.get("code"), e.get("voided")) for e in _v])
ok("void_note 在", all("R26事故回滚" in (e.get("void_note") or "") for e in _v))

print("== 3. sim_scheduler 代码版本守卫 ==")
spec = importlib.util.spec_from_file_location("ss_guard", os.path.join(HERE, "sim_scheduler.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)
ok("守卫监控 7 模块", len(ss._MTIME0) == 7, sorted(os.path.basename(p) for p in ss._MTIME0))
ok("含 paper_sim/execution/portfolio", any(p.endswith("paper_sim.py") for p in ss._MTIME0)
   and any(p.endswith("execution.py") for p in ss._MTIME0)
   and any(p.endswith("portfolio.py") for p in ss._MTIME0))
ok("初始未变 → None", ss._code_changed() is None)
# mtime 变化三态(触碰后还原)
_p = os.path.join(HERE, "core", "reason_enums.py")
_m0 = ss._MTIME0[_p]
os.utime(_p, (_t.time(), _t.time() + 5))
ok("mtime 变化 → 检出该文件", ss._code_changed() == _p, ss._code_changed())
os.utime(_p, (_m0, _m0))
ok("mtime 还原 → None", ss._code_changed() is None)
# 循环退出语义(源码)
src = open(os.path.join(HERE, "sim_scheduler.py"), encoding="utf-8").read()
ok("守卫退出 exit code 3", "sys.exit(3)" in src)
ok("守卫提示语在(撮合语义过期)", "撮合语义过期" in src)
ok("R26 事故复盘注释在", "R26 事故复盘" in src)

print("== 4. sim_scheduler 时区补齐(R21 遗漏) ==")
import ast as _ast
_tree = _ast.parse(src)
_fmt_calls = [n for n in _ast.walk(_tree) for a in _ast.walk(n)
              if isinstance(a, _ast.Attribute) and isinstance(a.value, _ast.Name)
              and a.value.id == "time" and a.attr == "strftime"]
ok("代码级 time.strftime 调用=0(仅 docstring 提及)", len(_fmt_calls) == 0, len(_fmt_calls))
ok("cn_now 单源在", "from core.time_cn import cn_now" in src)

print("== 5. R12-R25 修复保持 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("leg_flags 仍在", '"leg_flags"' in src_ps)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src_ps)
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("R24 开盘窗口 now 仍在", '_snap["now"] = cn_now(' in src_ps)
ok("R25 空价 TTL 推进仍在", "R25 TTL(行情不可用推进)" in src_ps)
ok("R23 日历 next_td 仍在", "from core.trading_calendar import next_td" in src_ps)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)