# -*- coding: utf-8 -*-
"""tests_audit_r8p.py —— R27(第八轮审计后续, R26 事故复盘深挖)回归锁:
交易时段守卫 —— 非 A 股交易时段(上海 09:30-11:30/13:00-15:00)不执行
撮合/平仓判定, 防止 Sina 盘后旧快照(上一交易日 px/open/high/low)被
当作实时数据回溯成交。

事故链(R26→R27):
- R26 事故: 旧进程(09-11 代码)午夜用周五旧 open 回溯成交 000157/002203;
- R27 发现: **新进程**(载 R12-R26 守卫)01:00 仍用周五极值撮合 002203
  触价(fill 19.472>=sl 18.864) —— R8 几何守卫拦截(首次实弹生效!)但
  揭示盲区: 若该单几何合法就成午夜错误成交。根因: 非交易时段 Sina
  返回上一交易日快照, 任何时段撮合=历史数据回溯。
"""
import os, sys, json, importlib.util
from datetime import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

print("== 1. 时段守卫源码接线 ==")
src = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("realtime_monitor 时段守卫在", "R27 交易时段守卫" in src)
ok("双时段判定(上午/下午)", "(930 <= _hm <= 1130) or (1300 <= _hm <= 1500)" in src)
ok("非交易日守卫在(R34: 周末规则+快照日期, is_td 移除)",
   "_wd >= 5" in src and "_fresh" in src,
   "R34 后: is_td(今天) 结构性误判已移除, 判据=周末规则+快照新鲜度")
ok("OFF_SESSION 日志记录", "OFF_SESSION" in src)
ok("非时段返回 0,0(不撮合不平仓)", "return 0, 0" in src.split("def realtime_monitor")[1][:2500])
ok("TTL 暂停的诚实注释在", "晚撤不早撤" in src)
# R34(2026-09-14): 失效模式翻转 —— 原 R27 fail-open("时区不可用继续跑")
# 在 R27 结构性误判事故后不再安全: 无日期判据的快照无法证明新鲜度,
# 继续跑会用旧快照回溯撮合(R26 事故同型) → fail-closed 暂停。
ok("解析失败 fail-closed(R34 翻转, 旧 fail-open 语义废弃)",
   "_in_session = False  # R34" in src)

print("== 2. 守卫行为(真实时间=01:xx 非时段) ==")
if not os.path.exists(os.path.join(HERE, "paper_ledger.json")):
    print("  SKIP 无运行时账本/日志")
    print("\n结果: PASS=%d FAIL=%d (数据依赖项跳过)" % (PASS, FAIL))
    sys.exit(0)
import paper_sim as PS
from core.time_cn import shanghai_now, cn_today
from core.trading_calendar import is_td
_hm = shanghai_now().hour * 100 + shanghai_now().minute
_in = (930 <= _hm <= 1130) or (1300 <= _hm <= 1500)
print(f"  当前 {shanghai_now().strftime('%H:%M')} is_td={is_td(cn_today())}")
# 当前(凌晨)非时段 → realtime_monitor 应返回 0,0 且不触碰账本
_before = json.dumps(json.load(open(os.path.join(HERE, "paper_ledger.json"), encoding="utf-8")), sort_keys=True)
_nf, _nc = PS.realtime_monitor()
_after = json.dumps(json.load(open(os.path.join(HERE, "paper_ledger.json"), encoding="utf-8")), sort_keys=True)
ok("非时段返回 0,0", (_nf, _nc) == (0, 0), (_nf, _nc))
ok("账本未被触碰(非时段)", _before == _after)
# realtime_log 有 OFF_SESSION 记录
lg = json.load(open(os.path.join(HERE, "realtime_log.json"), encoding="utf-8"))
_lgl = lg if isinstance(lg, list) else lg.get("log", [])
ok("OFF_SESSION 日志在案", any(e.get("status") == "OFF_SESSION" for e in _lgl[-10:]))

print("== 3. 时段语义单元(上海时区构造) ==")
def in_session(h, m):
    hm = h * 100 + m
    return (930 <= hm <= 1130) or (1300 <= hm <= 1500)
ok("09:30 恰开市", in_session(9, 30))
ok("10:15 开盘窗口尾", in_session(10, 15))
ok("11:30 午休开始", in_session(11, 30))
ok("11:31 午休", not in_session(11, 31))
ok("12:00 午休", not in_session(12, 0))
ok("13:00 下午开市", in_session(13, 0))
ok("15:00 收市", in_session(15, 0))
ok("15:01 收市后", not in_session(15, 1))
ok("01:00 凌晨(R27 事故时刻)", not in_session(1, 0))
ok("00:00 凌晨(R26 事故时刻)", not in_session(0, 0))

print("== 4. R8 守卫实弹拦截记录(002203) ==")
led = json.load(open(os.path.join(HERE, "paper_ledger.json"), encoding="utf-8"))
_203 = next((t for t in led if t.get("code") == "002203" and t.get("valid_from") == "20260914"), None)
ok("002203 已被 R8 撤单(EXPIRED)", _203 and _203["status"] == "EXPIRED", _203 and _203["status"])
ok("expire_reason=BAD_GEOMETRY_FILL_GE_SL", _203 and _203.get("expire_reason") == "BAD_GEOMETRY_FILL_GE_SL")
ok("R8 实弹拦截 note 在", _203 and "R8合同守卫" in (_203.get("note") or ""))
ok("002203 几何非法(limit>=sl)", _203 and float(_203.get("entry_price", 0)) >= float(_203.get("sl1", 0)))
_157 = next((t for t in led if t.get("code") == "000157" and t.get("valid_from") == "20260914"), None)
ok("000157 几何合法(limit<sl)保持 PENDING", _157 and _157["status"] == "PENDING_ORDER"
   and float(_157["entry_price"]) < float(_157["sl1"]), _157 and _157["status"])

print("== 5. R12-R26 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src)
ok("R24 开盘窗口 now 仍在", '_snap["now"] = cn_now(' in src)
ok("R25 空价 TTL 推进仍在", "R25 TTL(行情不可用推进)" in src)
ok("R26 守卫注释仍在(sim_scheduler)", "R26 事故复盘" in open(os.path.join(HERE, "sim_scheduler.py"), encoding="utf-8").read())

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
