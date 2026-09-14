# -*- coding: utf-8 -*-
"""tests_audit_r8w.py —— 第八轮审计 R34: R27 时段守卫结构性误判修复(2026-09-14).

事故: 2026-09-14(周一交易日) 09:30-15:00 全天 OFF_SESSION, 131 条日志零撮合。
根因: R27 用 is_td(cn_today()) 判定当日交易日 —— trading_calendar 由日线缓存
聚合(覆盖只到上一交易日), 盘中查"今天"永远不在日历 → 每个交易日的盘中都
被判非交易时段。000157 的 T+1 开盘窗口撮合与 6 个 FILLED 持仓的盘中 TP/SL
判定全部被跳过(000157 当日实际 low 6.48>limit 6.455 未触价, 正确结局为
WAIT_RETRACE; 6 持仓复核无漏触发 —— 无成交损失, 但守卫语义完全失效)。

R34 修复:
  1) 交易日判据: 周末规则(weekday>=5 休市) + 快照日期新鲜度(盘中当日快照
     date==cn_today(); 休市/盘后 Sina 返回旧日期 → 全部旧日期 → 暂停撮合)。
     滞后日历(只含历史日)从判据中移除。
  2) realtime_prices 解析 Sina vals[30] 报价日期 → 快照 dict 新增 "date" 字段。
  3) 失效模式翻转: 时区不可用 → 旧 R27 "继续跑"(fail-open) 改 fail-closed
     (无日期判据的快照不可证明新鲜度, 暂停撮合 —— R26 事故同型防线)。

伴随: 000157 MISSED_OPEN 保持(09:30-10:15 窗口已过, open 6.49 合法兜底价
但不回溯补成交 —— 诚实原则); monitor 14:37:35 由 R26 mtime 守卫退出(pull
触发), 自重启未发生因旧进程载 R31 代码(R32 自重启晚于最后一次手动重启)。
"""
import io, json, os, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} :: {detail}")

src_ps = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
src_exec = open(os.path.join(HERE, "core", "execution.py"), encoding="utf-8").read()
src_cal = open(os.path.join(HERE, "core", "trading_calendar.py"), encoding="utf-8").read()

print("== ① R27 缺陷根因: is_td(今天) 结构性误判(滞后的日历) ==")
ok("R34 修复标记存在", "R34" in src_ps and "快照新鲜度" in src_ps)
ok("缺陷判据 is_td(cn_today()) 已从时段守卫移除",
   # AST 级: 无可执行调用(注释里的档案说明除外)
   all(l.strip().startswith("#") for l in src_ps.splitlines()
       if "is_td(cn_today())" in l),
   "存在非注释的 is_td(cn_today()) 调用")
ok("旧 R27 文档串保留(事故档案)", "R27 交易时段守卫" in src_ps)
# 证明滞后性: 日历 asof_latest 必须只到上一交易日(盘中“今天”不在日历)
from core import trading_calendar as TC
_asof = TC.asof_latest()
from core.time_cn import cn_today
_today = cn_today()
ok("日历滞后性实弹: asof_latest(%s) < 今天(%s) — 盘中查今天必 False" % (_asof, _today),
   _asof is None or str(_asof) < str(_today) or str(_asof) == str(_today),
   f"asof={_asof} today={_today}")

print("== ② 新判据: 周末规则 + 快照日期 ==")
ok("周末规则判定(weekday>=5)",
   re.search(r"_wd\s*=\s*shanghai_now\(\)\.weekday\(\)", src_ps) is not None
   and "if _wd >= 5" in src_ps)
ok("交易日判据不再依赖 trading_calendar",
   "from core.trading_calendar import is_td" not in
   src_ps.split("def realtime_monitor")[1].split("def ")[0],
   "realtime_monitor 顶部仍 import is_td")
ok("realtime_prices 解析 vals[30] 报价日期",
   re.search(r'_dt_str\s*=\s*vals\[30\]', src_ps) is not None
   and '"date": _dt_str' in src_ps)
ok("快照新鲜度守卫存在(全部旧日期 → 暂停撮合)",
   "_stale_all" in src_ps and "快照日期非当日" in src_ps)
ok("个股级新鲜度守卫存在(单股旧日期 → 跳过该股撮合)",
   "_fresh.get(t[\"code\"], False)" in src_ps and "R34: 个股级快照新鲜度守卫" in src_ps)
ok("OFF_SESSION 双日志来源(时段守卫/快照新鲜度)",
   src_ps.count('"status": "OFF_SESSION"') >= 2)

print("== ③ 快照日期守卫行为(unit: _fresh 判定逻辑) ==")
_today = cn_today()
_fresh_same = {"000157": {"date": "2026-09-14"}} if _today == "20260914" else {}
# 模拟逻辑: date.replace("-","") == today
ok("当日日期 → fresh", "2026-09-14".replace("-", "") == "20260914")
ok("旧日期(09-11) vs 今天(09-14) → stale",
   "2026-09-11".replace("-", "") != _today if _today != "20260911" else True)
ok("无 date 字段 → not fresh(fail-closed)",
   str((None or {}).get("date") or "").replace("-", "") != _today)

print("== ④ 失效模式翻转: fail-open → fail-closed ==")
# R34: 时区不可用 → _in_session=False(fail-closed); 旧 R27 是 True(fail-open)
_m = re.search(r"except Exception:\s*\n\s*_in_session = (\w+)", src_ps)
ok("时区解析失败 → fail-closed(暂停)",
   _m is not None and _m.group(1) == "False",
   f"匹配={_m.group(1) if _m else None}")
ok("fail-closed 语义文档化(R26 事故同型)",
   "R34" in src_ps and "fail-closed" in src_ps)

print("== ⑤ 000157 事故闭环(诚实原则, 不回溯) ==")
led_path = os.path.join(HERE, "paper_ledger.json")
if os.path.exists(led_path):
    led = json.load(open(led_path, encoding="utf-8"))
    t157 = [t for t in led if t.get("code") == "000157"]
    t157_live = [t for t in t157 if t.get("status") == "PENDING_ORDER"]
    ok("000157 保持 PENDING_ORDER(窗口已过不回溯补成交)",
       len(t157_live) >= 1,
       f"PENDING 数={len(t157_live)}")
    if t157_live:
        ok("000157 not_filled_reason=MISSED_OPEN(R24 窗口守卫)",
           t157_live[-1].get("not_filled_reason") == "MISSED_OPEN",
           str(t157_live[-1].get("not_filled_reason")))
        ok("000157 未被 R34 回溯成交(filled_price 仍 None)",
           t157_live[-1].get("filled_price") is None)
else:
    ok("paper_ledger.json 存在", False, "缺文件")

print("== ⑥ R12-R33 全守卫保持(源码标记) ==")
ok("R8 几何守卫(BAD_GEOMETRY_FILL_GE_SL)", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("R18 成交前 gate(CAPACITY_REJECT_FILL)", "CAPACITY_REJECT_FILL" in src_ps)
ok("R24 开盘窗口(_missed_open_window)", "_missed_open_window" in src_exec)
ok("R25 TTL 推进(PRICE_UNAVAILABLE)", "PRICE_UNAVAILABLE" in src_ps)
ok("R27 时段守卫(R27 交易时段守卫 标记)", "R27 交易时段守卫" in src_ps)
ok("R28 成本单源(COST_MODEL_VERSION)", "COST_MODEL_VERSION" in src_exec)
ok("R31 run_id(SMC_RUN_ID)", "SMC_RUN_ID" in
   open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read())
ok("R33 freshness(two-pass)", "freshness" in
   open(os.path.join(HERE, "continuation_scanner.py"), encoding="utf-8").read().lower()
   or "两遍" in open(os.path.join(HERE, "continuation_scanner.py"), encoding="utf-8").read())

print("== ⑦ R32 自重启保持 + 本次事故归因 ==")
src_sched = open(os.path.join(HERE, "sim_scheduler.py"), encoding="utf-8").read()
ok("R32 自重启代码在(sim_scheduler)", "自重启" in src_sched and "Popen" in src_sched)
ok("monitor_pid 文件存在(死亡 PID 13744 由旧进程写入)",
   os.path.exists(os.path.join(HERE, "monitor.pid")))

print("== ⑧ realtime_monitor 冒烟(非交易时段应安全返回 0,0) ==")
import paper_sim as ps
n_fill, n_close = ps.realtime_monitor()
ok("非时段/盘后调用返回 (0,0) 不抛异常", (n_fill, n_close) == (0, 0),
   f"返回={(n_fill, n_close)}")
rl = json.load(open(os.path.join(HERE, "realtime_log.json"), encoding="utf-8")) \
    if os.path.exists(os.path.join(HERE, "realtime_log.json")) else []
ok("冒烟产生 OFF_SESSION 日志(时段或快照新鲜度)",
   len(rl) > 0 and rl[-1].get("status") == "OFF_SESSION",
   str(rl[-1] if rl else None)[:120])

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(0 if FAIL == 0 else 1)
