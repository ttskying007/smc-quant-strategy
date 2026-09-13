# -*- coding: utf-8 -*-
"""tests_reason_enums.py —— R7: reason 枚举权威源校验(P1清单#6, 2026-09-13)。
三层校验:
  1) 全链字面量源码扫描: core/execution.py / paper_sim.py / core/setup_exit.py /
     core/portfolio.py 产出的 reason/why/status 字面量 ⊆ 冻结枚举集(防新增未登记)
  2) 生产账本历史值校验: paper_ledger 每笔 exit_reason/not_filled_reason/status/entry_mode
     全部可解释(current/legacy), 无 UNKNOWN
  3) 枚举助手语义: is_known_exit_reason(None/current/legacy/未知), is_known_not_filled_why
"""
import io, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paper_sim  # noqa (先 import: 其 __main__ 不执行, 模块级不包 stdout)
from core.reason_enums import (EXIT_REASONS, NOT_FILLED_WHY, NOT_EXIT_WHY, ORDER_STATUS,  # noqa: E402
                               ENTRY_MODES, LEGACY_ENTRY_MODES, REJECT_STAGES, SL_REASONS,
                               SIM_REASONS, PAPER_EXITS, SE_STATUS, SE_EXIT_REASONS,
                               ENTRY_FILL_MODES, PF_REASONS, LEDGER_LEGACY_EXITS, DAY_STATUS,
                               EXPIRE_REASONS,
                               is_known_exit_reason, is_known_not_filled_why)

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

HERE = os.path.dirname(os.path.abspath(__file__))

print("== 1. 全链 reason/why 字面量 ⊆ 冻结枚举集 ==")
# 扫描产出点源码里的字符串字面量(只认赋值/字典值位置的枚举样式 token)
SCAN = {"core/execution.py", "paper_sim.py", "core/setup_exit.py", "core/portfolio.py",
        "core/entry.py", "core/reason_enums.py"}
ALLOWED = (EXIT_REASONS | NOT_FILLED_WHY | NOT_EXIT_WHY | ORDER_STATUS | ENTRY_MODES
           | LEGACY_ENTRY_MODES | SL_REASONS | SIM_REASONS | PAPER_EXITS | SE_STATUS
           | SE_EXIT_REASONS | ENTRY_FILL_MODES | PF_REASONS | DAY_STATUS | EXPIRE_REASONS
           | {"HOLD_EXIT", "unknown", "TIMEOUT", "INIT", "SL", "TP", "TIME"})
for fn in SCAN:
    fp = os.path.join(HERE, fn)
    src = open(fp, encoding="utf-8", errors="replace").read()
    # 抓 reason/why/status/mode 相关赋值: "reason": "X" / reason = "X" / mode": "X" ...
    found = set()
    for m in re.finditer(r'(?:reason|why|status|entry_mode|sl_reason|mode)["\']?\]?\s*[:=]\s*["\']([A-Za-z_][A-Za-z_0-9]*)["\']', src):
        v = m.group(1)
        if v in ("True", "False"):
            continue
        found.add(v)
    bad = sorted(v for v in found if v not in ALLOWED and not v.startswith("STAGE_"))
    ok(f"{fn} 字面量已登记({len(found)}种)", not bad, "未登记: " + ",".join(bad))

print("== 2. 生产账本历史值全部可解释 ==")
led = paper_sim.load_ledger()
bad_exit, bad_why, bad_st, bad_em, n_exit, n_why = [], [], [], [], 0, 0
for t in led:
    r = t.get("exit_reason")
    if r is not None:
        n_exit += 1
        good, _ = is_known_exit_reason(r)
        if not good:
            bad_exit.append((t.get("code"), r))
    w = t.get("not_filled_reason")
    if w is not None:
        n_why += 1
        good, _ = is_known_not_filled_why(w)
        if not good:
            bad_why.append((t.get("code"), w))
    if t.get("status") not in ORDER_STATUS:
        bad_st.append((t.get("code"), t.get("status")))
    em = t.get("entry_mode")
    if em is not None and em not in ENTRY_MODES and em not in LEGACY_ENTRY_MODES:
        bad_em.append((t.get("code"), em))
ok(f"exit_reason 全可解释(n={n_exit})", not bad_exit, bad_exit[:3])
ok(f"not_filled_reason 全可解释(n={n_why})", not bad_why, bad_why[:3])
ok(f"status 全合法(n={len(led)})", not bad_st, bad_st[:3])
ok(f"entry_mode 全合法", not bad_em, bad_em[:3])
# 历史遗留值分布(登记证据)
from collections import Counter
legacy = Counter(t.get("exit_reason") for t in led if t.get("exit_reason") == "HOLD_EXIT")
print(f"     (历史遗留 HOLD_EXIT: {dict(legacy) or '无'})")

print("== 3. 枚举助手语义 ==")
ok("exit None → open", is_known_exit_reason(None) == (True, "open"))
ok("exit SL_GAP → current", is_known_exit_reason("SL_GAP") == (True, "current"))
ok("exit TP2_RUNNER(simulate族) → current", is_known_exit_reason("TP2_RUNNER") == (True, "current"))
ok("exit PAPER_ADJUDICATE → paper_legacy", is_known_exit_reason("PAPER_ADJUDICATE") == (True, "paper_legacy"))
ok("exit HOLD_EXIT → paper_legacy", is_known_exit_reason("HOLD_EXIT")[1] == "paper_legacy")
ok("exit TP4_RUNNER → ledger_legacy", is_known_exit_reason("TP4_RUNNER") == (True, "ledger_legacy(v20f 旧组合带)"))
ok("exit 未知 → False", is_known_exit_reason("TP9")[0] is False)
ok("why None → missing(失败)", is_known_not_filled_why(None) == (False, "missing"))
ok("why WAIT_RETRACE → current", is_known_not_filled_why("WAIT_RETRACE") == (True, "current"))
ok("why unknown → legacy", is_known_not_filled_why("unknown")[0] is True)
ok("why 未知 → False", is_known_not_filled_why("NOPE")[0] is False)

print("== 4. 集合完整性 ==")
ok("EXIT_REASONS 8 种(含 SUSPENDED/TP2)", len(EXIT_REASONS) == 8 and "SUSPENDED" in EXIT_REASONS and "TP2" in EXIT_REASONS)
ok("TP1/TP2/TP3 在退出集", {"TP1", "TP2", "TP3"} <= EXIT_REASONS)
ok("SIM 族 6 种(TP2_RUNNER/BAD_ENTRY 等)", SIM_REASONS == {"TP2_RUNNER", "TP3_RUNNER", "TP_STRUCTURAL",
   "SKIP_LIMIT_UP", "BAD_ENTRY", "BAD_SIGNAL"})
ok("PAPER 裁决族(PAPER_ADJUDICATE+HOLD_EXIT)", PAPER_EXITS == {"PAPER_ADJUDICATE", "HOLD_EXIT"})
ok("账本历史族(TP4_RUNNER/TP_HIT)", LEDGER_LEGACY_EXITS == {"TP4_RUNNER", "TP_HIT"})
ok("setup_exit 5 status + 5 exit", SE_STATUS == {"SL", "TP", "TIME", "INVALIDATED", "OPEN"}
   and SE_EXIT_REASONS == {"SL_HIT", "TP_STRUCT", "TIME_STOP", "INVALIDATED_BEFORE_FILL", "NOT_YET"})
ok("ENTRY_MODES 三显式模式", ENTRY_MODES == {"limit_retrace", "limit_or_open", "next_open"})
ok("LEGACY 仅 retrace 别名", LEGACY_ENTRY_MODES == {"retrace"})
ok("ORDER_STATUS 四态", ORDER_STATUS == {"PENDING_ORDER", "FILLED", "EXPIRED", "CLOSED"})
ok("SL_REASONS 四种(R2+R7实测)", SL_REASONS == {"INIT", "TP1_MOVE_TO_BE", "SL_TOUCH_INTRADAY", "SL_GAP_OPEN_BELOW_STOP"})
ok("reject 五类+STAGE_前缀(R8+BAD_SL_GE_ENTRY)", REJECT_STAGES == {"EVENT_FILTER", "DUP_EXISTING", "DATA_MISSING", "ADX_LT20", "BAD_SL_GE_ENTRY"})
ok("EXPIRE_REASONS(R8 守卫+TIMEOUT)", EXPIRE_REASONS == {"BAD_GEOMETRY_FILL_GE_SL", "TIMEOUT"})
ok("DAY_STATUS 四态(R14)", DAY_STATUS == {"OK", "WEEKEND", "HOLIDAY_OR_NO_DATA", "NO_SIGNAL"})
ok("ENTRY_FILL_MODES 四种(含 MARKET_OPEN)", ENTRY_FILL_MODES == {"STRICT_LIMIT", "LIMIT_OR_OPEN", "INVALIDATED_BEFORE_FILL", "MARKET_OPEN"})
ok("NOT_EXIT_WHY 含 T1_LOCKED 六种", NOT_EXIT_WHY == {"LIMIT_DOWN_SELL", "BAD_POSITION", "HOLD", "NO_PRICE", "SUSPENDED", "T1_LOCKED"})

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)