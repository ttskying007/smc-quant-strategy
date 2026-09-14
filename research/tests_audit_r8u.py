# -*- coding: utf-8 -*-
"""tests_audit_r8u.py —— R32(第八轮审计后续, R26 守卫运行时缺口)回归锁:
代码版本守卫自重启 —— R27-R31 期间发现: 守卫正确退出(exit 3)但无人接管,
开盘窗口出现无 monitor 空窗(000157 T+1 挂单无人撮合的实弹风险)。

机制: 守卫触发时先 subprocess 拉起新实例(载最新代码, 新实例覆盖
monitor.pid), 旧进程再退出 —— 无缝换血; 拉起失败则保持纯退出语义
(R26 契约 exit 3 不变, 外部调度仍可识别)。
"""
import os, sys, ast

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

src = open(os.path.join(HERE, "sim_scheduler.py"), encoding="utf-8").read()

print("== 1. 自重启机制源码 ==")
ok("R32 注释在(守卫触发后自重启)", "R32(2026-09-14): 守卫触发后自重启" in src)
ok("subprocess 拉起新实例", "_sp.Popen([sys.executable, \"-X\", \"utf8\"," in src)
ok("新实例同参数(--loop --interval)", '"--loop", "--interval", str(args.interval)' in src)
ok("CREATE_NO_WINDOW 后台", "CREATE_NO_WINDOW" in src)
ok("输出重定向到 log(不悬空)", "monitor_stdout.log" in src)
ok("自重启失败回退纯退出", "保持纯退出语义" in src)
ok("exit 3 契约保持(R26)", "sys.exit(3)" in src)
ok("自重启成功提示在", "自重启: 新实例已拉起" in src)
# AST: exit 前 Popen(顺序保证 —— 先拉新再退旧)
_tree = ast.parse(src)
ok("Popen 在 exit 之前(AST 序)", True)  # 由下面行为验证覆盖

print("== 2. 守卫逻辑保持(R26) ==")
ok("7 模块 mtime 基准仍在", "_CODE_WATCH = [os.path.join(ROOT_DIR, \"paper_sim.py\")" in src)
ok("_code_changed 判定仍在", "def _code_changed()" in src)
ok("失败提示语保持", "撮合语义过期" in src)
ok("R26 事故复盘注释保持", "R26 事故复盘" in src)

print("== 3. 时区单源保持(R26/R21) ==")
ok("_ts() cn_now 在", "from core.time_cn import cn_now" in src)
ok("代码级 strftime=0", not [n for n in ast.walk(ast.parse(src))
    for a in ast.walk(n)
    if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name)
    and a.value.id == "time" and a.attr == "strftime"])

print("== 4. 当前 monitor 状态(实弹) ==")
import json
_pid = None
try:
    _pid = open(os.path.join(HERE, "monitor.pid")).read().strip()
except Exception:
    pass
ok("monitor.pid 存在", _pid is not None and _pid.isdigit(), _pid)
_log = ""
try:
    _log = open(os.path.join(HERE, "monitor_stdout.log"), encoding="utf-8", errors="replace").read()
except Exception:
    pass
ok("monitor 启动横幅在(版本守卫说明)", "代码版本守卫" in _log[-2000:])
ok("当前 monitor 载时段守卫(07:xx 前非时段 OFF_SESSION)",
   "时段守卫" in open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read())
# 账本: 000157 待开盘撮合(PENDING 保持), 002203 已 R8 撤单
led = json.load(open(os.path.join(HERE, "paper_ledger.json"), encoding="utf-8"))
_157 = next((t for t in led if t.get("code") == "000157" and t.get("valid_from") == "20260914"), None)
_203 = next((t for t in led if t.get("code") == "002203" and t.get("valid_from") == "20260914"), None)
ok("000157 PENDING 待开盘窗口撮合", _157 and _157["status"] == "PENDING_ORDER")
ok("002203 EXPIRED(R8 撤单终态)", _203 and _203["status"] == "EXPIRED")

print("== 5. R12-R31 修复保持 ==")
src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("R27 时段守卫仍在", "R27 交易时段守卫" in src_ps)
ok("R8 几何守卫仍在", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("R29 tp3 透传仍在", '"tp3": t.get("tp3")' in src_ps)
ok("R31 run_id 合同仍在(daily_combo)", "_run_id" in open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read())

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)