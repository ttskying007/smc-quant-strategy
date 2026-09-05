# -*- coding: utf-8 -*-
"""core/ledger_types.py 单元测试（蓝图迭代八）"""
import io, os, sys, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import ledger_types as LT

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + detail)

print("== 四本账类型 ==")
ok("4 种类型", LT.LEDGER_TYPES == ("backtest", "paper", "shadow", "live"))
ok("文件名", LT.ledger_book("shadow") == "shadow_ledger.json")
try:
    LT.ledger_book("bad")
    ok("非法类型拒绝", False)
except ValueError:
    ok("非法类型拒绝", True)

print("== 交易标注 ==")
tr = LT.annotate_trade({"symbol": "600519"}, "shadow", run_id="run-9")
ok("ledger_type=shadow", tr["ledger_type"] == "shadow")
ok("run_id 注入", tr["run_id"] == "run-9")

print("== research→shadow 门禁 ==")
ok_ok, failed = LT.gate_research_to_shadow({"no_lookahead": True, "oos_pass": True, "wf_pass": True})
ok("全过 → 通过", ok_ok and not failed)
ok_fail, failed2 = LT.gate_research_to_shadow({"no_lookahead": True, "oos_pass": False, "wf_pass": True})
ok("OOS未过 → 拒绝", not ok_fail and "oos_pass" in failed2)

print("== shadow→live 门禁 ==")
good = {"consecutive_stable_days": 35, "fill_deviation_pct": 0.2, "max_fill_dev_pct": 0.5,
        "has_data_gap": False, "signal_volume_drift": 0.1, "rollback_version": "v20f"}
g_ok, g_fail, req = LT.gate_shadow_to_live(good)
ok("shadow达标 → live", g_ok, str(g_fail))
bad = dict(good); bad["consecutive_stable_days"] = 5
g_ok2, g_fail2, _ = LT.gate_shadow_to_live(bad)
ok("观察不足30日 → 拒绝", not g_ok2 and "consecutive_stable" in g_fail2)

print("== manifest fail-closed ==")
with tempfile.TemporaryDirectory() as td:
    ok_r, why = LT.require_manifest(td)
    ok("无 manifest → fail-closed", not ok_r, why)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
