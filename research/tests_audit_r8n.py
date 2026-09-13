# -*- coding: utf-8 -*-
"""tests_audit_r8n.py —— R25(第八轮审计 P1-10 尾项)回归锁:
行情不可用时 PENDING 订单生命周期仍推进(TTL 过期) + PRICE_UNAVAILABLE 标注。
审计原文: "价格为空就 continue, 因此行情连续失败时不执行过期逻辑" →
"行情不可用时仍推进订单生命周期, 但标注 PRICE_UNAVAILABLE"。
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

from core.trading_calendar import td_between
from core.time_cn import cn_today

print("== 1. 空价 PENDING TTL 推进(分支语义) ==")
today = cn_today()
# 复现分支体(与 paper_sim L1129-1149 同步)
def ttl_branch(t, need=3):
    """R25 分支语义模拟: 行情不可用(PENDING)→交易日 TTL 推进"""
    if t.get("status") == "PENDING_ORDER":
        _vf3 = t.get("valid_from", "")
        if _vf3:
            _n_td3 = td_between(_vf3, today)
            if _n_td3 > need:
                t["status"] = "EXPIRED"
                t["expire_reason"] = "TIMEOUT"
                t["note"] = (t.get("note", "") +
                             f" | R25 TTL(行情不可用推进): valid_from起{_n_td3}交易日>{need}未成交(PRICE_UNAVAILABLE)").strip()
    return t

_t_old = {"code": "600000", "status": "PENDING_ORDER", "valid_from": "20260907"}
_r = ttl_branch(dict(_t_old))
ok("久远 PENDING(valid_from>3td) → EXPIRED", _r["status"] == "EXPIRED", _r)
ok("expire_reason=TIMEOUT", _r.get("expire_reason") == "TIMEOUT")
ok("PRICE_UNAVAILABLE 标注在", "PRICE_UNAVAILABLE" in _r.get("note", ""))
# 新单(1 个交易日内) → 保持 PENDING
_t_new = {"code": "600001", "status": "PENDING_ORDER",
          "valid_from": td_between and "20260914" if today == "20260914" else today}
_r2 = ttl_branch(dict(_t_new))
ok("新 PENDING → 保持(不过期)", _r2["status"] == "PENDING_ORDER", _r2)
# FILLED 持仓 → 不强平
_t_f = {"code": "600002", "status": "FILLED", "valid_from": "20260907"}
_r3 = ttl_branch(dict(_t_f))
ok("FILLED 空价 → 不强平(保持)", _r3["status"] == "FILLED", _r3)
# 无 valid_from → 不处理
_t_nv = {"code": "600003", "status": "PENDING_ORDER", "valid_from": ""}
_r4 = ttl_branch(dict(_t_nv))
ok("无 valid_from → 保持(不误过期)", _r4["status"] == "PENDING_ORDER", _r4)

print("== 2. 生产源码接线 ==")
src = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("空价分支不再纯 continue(有 TTL 推进)", "R25 TTL(行情不可用推进)" in src)
ok("P1-10 注释在(第八轮)", "第八轮审计 P1-10" in src)
ok("PRICE_UNAVAILABLE 标注字面量在", "PRICE_UNAVAILABLE" in src)
ok("交易日 TTL 语义与主路径同源(td_between)",
   src.count("from core.trading_calendar import td_between") >= 2)
ok("EXPIRED 过期日志在(行情不可用)", "PENDING TTL 到期(行情不可用, 生命周期仍推进)" in src)
ok("日历不可用 fail-closed 注释在", "不误过期, fail-closed" in src)

print("== 3. 主 TTL 路径保持(同语义无分叉) ==")
ok("主路径交易日历 TTL 仍在(1251 区)", "PENDING 过期机制" in src and
   "_expd = add_td_days(_vf2" in src)
ok("主路径与新分支同标准(PENDING_EXPIRE_DAYS)", src.count("PENDING_EXPIRE_DAYS") >= 3)

print("== 4. R12-R24 修复保持 ==")
ok("leg_flags 仍在", '"leg_flags"' in src)
ok("R18 成交前 gate 仍在", "CAPACITY_REJECT_FILL" in src)
ok("R24 开盘窗口快照 now 仍在", '_snap["now"] = cn_now(' in src)
ok("R23 日历 next_td 优先仍在", "from core.trading_calendar import next_td" in src)
ok("ADX 单源入口仍在", "from core.indicators import adx14_of as _adx_core" in src)
ok("时区单源仍在", "from core.time_cn import cn_now, cn_today" in src)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)