# -*- coding: utf-8 -*-
"""tests_audit_funnel_diagnostic.py — 选股漏斗分层诊断回归锁(审计§8.1/§8.2)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "v25"))
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  OK " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + " " + str(detail))


from funnel_diagnostic import (STAGES, report, stage_breakdown,
                               diagnose_zero)  # noqa: E402

print("== 1. 漏斗 7 层定义(§8.2 顺序) ==")
ok("7 层齐全", len(STAGES) == 7, STAGES)
ok("层序正确", [s[0] for s in STAGES] == [
    "1_data_fresh", "2_swing_confirmed", "3_sweep_reclaim",
    "4_response_break", "5_visible_target", "6_research_gate",
    "7_open_in_range"], [s[0] for s in STAGES])

print("== 2. 分层报告(进入/通过/通过率) ==")
r = report(
    {"1_data_fresh": 100, "2_swing_confirmed": 60, "3_sweep_reclaim": 30,
     "4_response_break": 15, "5_visible_target": 8, "6_research_gate": 3,
     "7_open_in_range": 2},
    {"NO_SWING": 40, "NO_RESPONSE": 15, "NO_TARGET": 7, "GATE_FAIL": 5,
     "OPEN_GAP": 1})
ok("报告含 7 层", len(r["stages"]) == 7, len(r["stages"]))
ok("第1层 100 进入", r["stages"][0]["entered"] == 100, r["stages"][0])
ok("通过率计算(60/100=60%)", abs(r["stages"][0]["pass_rate_pct"] - 60.0) < 1e-9,
   r["stages"][0])
ok("拒绝原因分组", r["reject_by_reason"]["NO_SWING"] == 40, r["reject_by_reason"])
ok("最终候选 = 2", r["n_final"] == 2, r["n_final"])

print("== 3. 按维度分布(§8.1) ==")
cands = {
    "1_data_fresh": [{"symbol": "A", "year": "2024", "market_phase": "up"},
                     {"symbol": "B", "year": "2024", "market_phase": "up"},
                     {"symbol": "C", "year": "2025", "market_phase": "down"}],
    "7_open_in_range": [{"symbol": "A", "year": "2024", "market_phase": "up"}],
}
bd = stage_breakdown(cands, dim="year")
ok("按年分布: 2024=2", bd["1_data_fresh"]["2024"] == 2, bd)
ok("最终层: 2024=1", bd["7_open_in_range"]["2024"] == 1, bd)
bd2 = stage_breakdown(cands, dim="market_phase")
ok("按市场状态分布: up=2", bd2["1_data_fresh"]["up"] == 2, bd2)

print("== 4. 零候选定位(§8.2 语义) ==")
# 场景A: 第6层为零(gate) -> 经济门槛正确生效
f1 = {"1_data_fresh": 100, "2_swing_confirmed": 60, "3_sweep_reclaim": 30,
      "4_response_break": 15, "5_visible_target": 8, "6_research_gate": 0}
d1 = diagnose_zero(f1)
ok("第6层为零 -> 定位 gate", d1["zero_stage"] == "6_research_gate", d1)
ok("gate 为零 = 经济门槛正确生效", d1["is_gate_ok"] is True, d1)

# 场景B: 第1层为零(数据未刷新) -> 数据管线问题
d2 = diagnose_zero({"1_data_fresh": 0})
ok("第1层为零 -> 数据未刷新", d2["zero_stage"] == "1_data_fresh", d2)
ok("非经济门槛(是数据问题)", d2["is_gate_ok"] is False, d2)

# 场景C: 第7层为零(可成交性) -> 执行过滤
f3 = {"1_data_fresh": 10, "2_swing_confirmed": 10, "3_sweep_reclaim": 10,
      "4_response_break": 10, "5_visible_target": 10, "6_research_gate": 10,
      "7_open_in_range": 0}
d3 = diagnose_zero(f3)
ok("第7层为零 -> 可成交性过滤", d3["zero_stage"] == "7_open_in_range", d3)
ok("执行过滤标记", d3["is_exec_filter"] is True, d3)

# 场景D: 各层有量但最终 0 -> 查拒绝原因
d4 = diagnose_zero({"1_data_fresh": 10, "2_swing_confirmed": 10,
                    "3_sweep_reclaim": 10, "4_response_break": 10,
                    "5_visible_target": 10, "6_research_gate": 10,
                    "7_open_in_range": 0})
ok("第7层后仍0 -> 需查拒绝原因", d4["zero_stage"] == "7_open_in_range", d4)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)