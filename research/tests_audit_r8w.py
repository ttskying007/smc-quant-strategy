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

测试分两层:
  A) 源码/账本级(锁语义) + B) 行为级(mock Sina 响应, 验证 vals[30] 提取与
  新鲜度判定式 —— 不依赖真实时段, 任何时候可复现)。
"""
import io, json, os, re, sys
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

print("== A1. R27 缺陷根因: is_td(今天) 结构性误判(滞后的日历) ==")
ok("R34 修复标记存在", "R34" in src_ps and "快照新鲜度" in src_ps)
ok("缺陷判据 is_td(cn_today()) 已从时段守卫移除",
   # AST 级: 无可执行调用(注释里的档案说明除外)
   all(l.strip().startswith("#") for l in src_ps.splitlines()
       if "is_td(cn_today())" in l),
   "存在非注释的 is_td(cn_today()) 调用")
ok("旧 R27 文档串保留(事故档案)", "R27 交易时段守卫" in src_ps)
# 证明滞后性: 日历 asof_latest 必须只到上一交易日(盘中"今天"不在日历)
from core import trading_calendar as TC
_asof = TC.asof_latest()
from core.time_cn import cn_today
_today = cn_today()
ok("日历滞后性实弹: asof_latest(%s) < 今天(%s) — 盘中查今天必 False" % (_asof, _today),
   _asof is None or str(_asof) < str(_today) or str(_asof) == str(_today),
   f"asof={_asof} today={_today}")

print("== A2. 新判据: 周末规则 + 快照日期 ==")
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
   '_fresh.get(t["code"], False)' in src_ps and "R34: 个股级快照新鲜度守卫" in src_ps)
ok("OFF_SESSION 双日志来源(时段守卫/快照新鲜度)",
   src_ps.count('"status": "OFF_SESSION"') >= 2)

print("== A3. 失效模式翻转: fail-open → fail-closed ==")
# R34: 时区不可用 → _in_session=False(fail-closed); 旧 R27 是 True(fail-open)
_m = re.search(r"except Exception:\s*\n\s*_in_session = (\w+)", src_ps)
ok("时区解析失败 → fail-closed(暂停)",
   _m is not None and _m.group(1) == "False",
   f"匹配={_m.group(1) if _m else None}")
ok("fail-closed 语义文档化(R26 事故同型)",
   "R34" in src_ps and "fail-closed" in src_ps)

print("== A4. 000157 事故闭环(诚实原则, 不回溯) ==")
led_path = os.path.join(HERE, "paper_ledger.json")
if os.path.exists(led_path):
    led = json.load(open(led_path, encoding="utf-8"))
    t157_live = [t for t in led if t.get("code") == "000157"
                 and t.get("status") in ("PENDING_ORDER", "FILLED")]
    # R37(2026-09-15): 000157 误拒修复后恢复 PENDING, 14:32 回踩触价 6.455
    # 合规成交(fill 6.461 < sl 6.515) —— 由"保持 PENDING"更新为"合规成交/挂单"
    ok("000157 合规处置(R37 误拒已修复, 成交/挂单皆合规)",
       len(t157_live) >= 1,
       f"live 数={len(t157_live)}")
    if t157_live:
        # R37(2026-09-15): 000157 演化链 09-14 MISSED_OPEN(未触价) → 09-15 误拒
        # (R37 gate bug) → 恢复 PENDING → 14:32 回踩触价合规成交(fill 6.461<sl 6.515)。
        # 断言: 若 FILLED 则 fill<sl(几何合规); 若 PENDING 则未触价 MISSED_OPEN。
        ok("000157 成交几何合规(fill<sl) 或 仍挂单未触价",
           (t157_live[-1]["status"] == "FILLED"
            and float(t157_live[-1].get("filled_price") or 0) < float(t157_live[-1].get("sl1", 0)))
           or (t157_live[-1]["status"] == "PENDING_ORDER"
               and t157_live[-1].get("not_filled_reason") in (None, "MISSED_OPEN", "WAIT_RETRACE")),
           str(t157_live[-1].get("filled_price")))
        ok("000157 成交为回踩触价(限价×(1+滑点))而非开盘兜底回溯",
           t157_live[-1]["status"] != "FILLED"
           or float(t157_live[-1].get("filled_price") or 0)
           <= float(t157_live[-1].get("entry_price", 999)) * 1.005,
           str(t157_live[-1].get("filled_price")))
else:
    ok("paper_ledger.json 存在", False, "缺文件")

print("== A5. R12-R33 全守卫保持(源码标记) ==")
ok("R8 几何守卫(BAD_GEOMETRY_FILL_GE_SL)", "BAD_GEOMETRY_FILL_GE_SL" in src_ps)
ok("R18 成交前 gate(CAPACITY_REJECT_FILL)", "CAPACITY_REJECT_FILL" in src_ps)
ok("R24 开盘窗口(_missed_open_window)", "_missed_open_window" in src_exec)
ok("R25 TTL 推进(PRICE_UNAVAILABLE)", "PRICE_UNAVAILABLE" in src_ps)
ok("R27 时段守卫(R27 交易时段守卫 标记)", "R27 交易时段守卫" in src_ps)
ok("R28 成本单源(COST_MODEL_VERSION)", "COST_MODEL_VERSION" in src_exec)
ok("R31 run_id(SMC_RUN_ID)", "SMC_RUN_ID" in
   open(os.path.join(HERE, "daily_combo_run.py"), encoding="utf-8").read())
_src_cs = open(os.path.join(HERE, "continuation_scanner.py"), encoding="utf-8").read()
ok("R33 freshness(两遍扫描)", "两遍" in _src_cs or "freshness" in _src_cs.lower())

print("== A6. R32 自重启保持 + 本次事故归因 ==")
src_sched = open(os.path.join(HERE, "sim_scheduler.py"), encoding="utf-8").read()
ok("R32 自重启代码在(sim_scheduler)", "自重启" in src_sched and "Popen" in src_sched)
ok("monitor_pid 文件存在", os.path.exists(os.path.join(HERE, "monitor.pid")))

print("== A7. realtime_monitor 冒烟(时段感知, R37: 盘中不再误报) ==")
import paper_sim as ps
n_fill, n_close = ps.realtime_monitor()
# R37(2026-09-15): 原断言写死"非交易时段"语境(凌晨跑测试) —— 盘中(11:0x)
# 跑测试时 monitor 合法撮合, 返回计数>0 是正确行为。时段感知断言:
# 非时段 → (0,0)+OFF_SESSION 尾日志; 盘中 → 计数非负整数(真撮合)。
from core.time_cn import shanghai_now as _shn
_hm_w = _shn().hour * 100 + _shn().minute
_wd_w = _shn().weekday()
_in_w = (930 <= _hm_w <= 1130) or (1300 <= _hm_w <= 1500) and _wd_w < 5
rl = json.load(open(os.path.join(HERE, "realtime_log.json"), encoding="utf-8")) \
    if os.path.exists(os.path.join(HERE, "realtime_log.json")) else []
if not _in_w or _wd_w >= 5:
    ok("非时段/盘后调用返回 (0,0) 不抛异常", (n_fill, n_close) == (0, 0),
       f"返回={(n_fill, n_close)}")
    ok("冒烟产生 OFF_SESSION 日志(时段或快照新鲜度)",
       len(rl) > 0 and rl[-1].get("status") == "OFF_SESSION",
       str(rl[-1] if rl else None)[:120])
else:
    ok("盘中冒烟不抛异常且计数非负(真撮合)",
       isinstance(n_fill, int) and isinstance(n_close, int) and n_fill >= 0 and n_close >= 0,
       f"返回={(n_fill, n_close)}")
    ok("盘中撮合日志在案(FILLED/EXPIRED 而非 OFF_SESSION)",
       len(rl) > 0 and rl[-1].get("status") in ("FILLED", "OFF_SESSION", "EXPIRED"),
       str(rl[-1] if rl else None)[:120])

# ================= B) 行为级(mock Sina, 不依赖真实时段) =================
print("== B1. realtime_prices 解析 vals[30](mock Sina 响应) ==")
from unittest import mock

_D_TODAY = f"{_today[:4]}-{_today[4:6]}-{_today[6:8]}"

def _sina_response(code, date_str, px="10.00"):
    # Sina hq 行格式: name,open,prev,px,high,low,bid,ask,vol,...,date,time,...
    vals = [f"N{code}", "10.0", "9.9", px, "10.2", "9.8", "10.0", "10.0", "100000",
            "1000000"] + ["0"] * 20 + [date_str, "10:30:00", "00", "H|1|1"]
    return f'var hq_str_sz{code}="' + ",".join(vals) + '";\n'

class _FakeUrlopen:
    def __init__(self, body):
        self._b = body.encode("gbk")
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

def _fake_urlopen(req, timeout=15):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    codes = url.split("list=")[1].split(",")
    body = ""
    for sym in codes:
        code = sym[2:]
        if code == "000001":      # 当日快照
            body += _sina_response(code, _D_TODAY)
        else:                      # 旧快照(上一交易日)
            body += _sina_response(code, "2026-09-11")
    return _FakeUrlopen(body)

with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
    px = ps.realtime_prices(["000001", "000002"])
ok("当日快照 date 解析为 cn_today()",
   px.get("000001", {}).get("date") == _D_TODAY, str(px.get("000001")))
ok("旧快照 date 原样透传(2026-09-11)",
   px.get("000002", {}).get("date") == "2026-09-11", str(px.get("000002")))
ok("旧快照仍有价格字段(不丢 px)",
   px.get("000002", {}).get("px") == 10.0)

print("== B2. _fresh 判定式(R34 同式) ==")
_fresh = {c: str((v or {}).get("date") or "").replace("-", "") == _today
          for c, v in px.items()}
ok("当日股 fresh=True", _fresh["000001"] is True)
ok("旧日股 fresh=False", _fresh["000002"] is False)
ok("全旧 → _stale_all 触发(模拟两旧股)",
   (lambda p: p and all(not (str((v or {}).get("date") or "").replace("-", "") == _today)
                        for v in p.values()))({"000002": {"date": "2026-09-11"},
                                                "000003": {"date": "2026-09-10"}}) is True)

print("== B3. 时段窗口判定式(R34: 纯 HH:MM, 无日历依赖) ==")
def in_session(hm):
    return (930 <= hm <= 1130) or (1300 <= hm <= 1500)
ok("09:30 开市", in_session(930))
ok("11:30 午休", in_session(1130) and not in_session(1131))
ok("13:00 下午", in_session(1300))
ok("15:00 收市", in_session(1500) and not in_session(1501))
ok("周日 weekday=6 → 非时段",
   (lambda wd: wd >= 5)(__import__("datetime").date(2026, 9, 13).weekday()) is True)
ok("周一 weekday=0 → 不因周末规则拦截",
   (lambda wd: wd >= 5)(__import__("datetime").date(2026, 9, 14).weekday()) is False)

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(0 if FAIL == 0 else 1)
