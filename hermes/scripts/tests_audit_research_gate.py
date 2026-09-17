# -*- coding: utf-8 -*-
"""tests_audit_research_gate.py — 预注册研究门槛回归锁(审计§10.3/Iteration 3)."""
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


from research_gate import (GATE, evaluate, monthly_span, _pct_metrics)  # noqa: E402


def ledger(n, year="2024", month="01", avg=1.0, wr=0.6):
    """构造 n 笔台账(avg% 平均净收益, wr 胜率)."""
    rows = []
    import random
    rng = random.Random(42)
    for i in range(n):
        won = rng.random() < wr
        # 近似: 使均值约 avg
        val = avg * 2 if won else -avg * (1 - wr) / wr
        rows.append({"entry_date": "%s-%s-01" % (year, month),
                     "net_pnl_pct": val, "gross_pnl_pct": val})
    return rows


def ledger_spread(n, year="2024", avg=1.5, wr=0.6):
    """n 笔均匀分布到全年 12 个月(避免零交易月)."""
    rows = []
    import random
    rng = random.Random(7)
    per_month = n // 12
    for m in range(1, 13):
        for i in range(per_month):
            won = rng.random() < wr
            val = avg * 2 if won else -avg * (1 - wr) / wr
            rows.append({"entry_date": "%s-%02d-%02d" % (year, m, i % 28 + 1),
                         "net_pnl_pct": val, "gross_pnl_pct": val})
    return rows


print("== 1. 门槛常量预注册(§10.3) ==")
ok("GATE 含全部审计门槛", all(k in GATE for k in (
    "n_min", "yearly_n_min", "wr_min", "avg_net_pnl_pct_min",
    "pf_min", "payoff_min", "monthly_trade_count_min_exclusive")), GATE)
ok("n_min=1000", GATE["n_min"] == 1000, GATE["n_min"])
ok("wr_min=55", GATE["wr_min"] == 55.0, GATE["wr_min"])
ok("pf_min=1.15", GATE["pf_min"] == 1.15, GATE["pf_min"])
ok("payoff_min=0.70", GATE["payoff_min"] == 0.70, GATE["payoff_min"])

print("== 2. 达标场景(全门槛通过) ==")
# 构造: 3000 笔 2023-2026, WR 60%, 平均 +1.5%(PF/Payoff 应高)
rows = []
for y in ("2023", "2024", "2025", "2026"):
    rows += ledger_spread(744, year=y, avg=1.5, wr=0.6)
r = evaluate(rows)
ok("达标 -> passed=True", r["passed"] is True,
   {k: v for k, v in r["checks"].items() if not v["ok"]})

print("== 3. 不达标场景(总 n 不足) ==")
r2 = evaluate(ledger(50, year="2024", avg=2.0, wr=0.7))
ok("n=50 < 1000 -> 不通过", r2["passed"] is False, r2["checks"]["total_n"])
ok("n 检查标注不足", r2["checks"]["total_n"]["ok"] is False, r2["checks"]["total_n"])

print("== 4. 零交易月不隐藏(§10.3 月度完整区间) ==")
# 仅 1 月有交易, 3 月也有; 2 月为零
rows4 = ledger(1200, year="2024", month="01", avg=1.5, wr=0.6) + \
        ledger(600, year="2024", month="03", avg=1.5, wr=0.6)
span = monthly_span(rows4)
ok("月度完整区间含 1-3 月", list(span.keys()) == ["202401", "202402", "202403"], span)
ok("2 月零交易被列出", span.get("202402") == 0, span)
r4 = evaluate(rows4)
ok("零交易月 -> 月度门槛不通过", r4["checks"]["monthly_span"]["ok"] is False,
   r4["checks"]["monthly_span"])

print("== 5. 逐年检查(某年净收益为负 -> 不通过) ==")
rows5 = [{"entry_date": "2023-%02d-%02d" % (m, d % 28 + 1),
            "net_pnl_pct": -1.2, "gross_pnl_pct": -1.0}
           for m in range(1, 13) for d in range(63)] + \
        ledger_spread(744, year="2024", avg=2.0, wr=0.7) + \
        ledger_spread(744, year="2025", avg=2.0, wr=0.7) + \
        ledger_spread(744, year="2026", avg=2.0, wr=0.7)
r5 = evaluate(rows5)
ok("2023 年负收益被检出", r5["yearly"]["2023"]["avg_ok"] is False,
   r5["yearly"]["2023"])
ok("总判定不通过", r5["passed"] is False, r5["checks"]["yearly_2023_avg_net"])

print("== 6. T+1/前视/oracle 违规 ==")
rows6 = ledger(1200, year="2024", avg=2.0, wr=0.7)
r6 = evaluate(rows6, t1_violations=1)
ok("T+1 违规 1 -> 不通过", r6["passed"] is False, r6["checks"]["t1_violations"])

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)