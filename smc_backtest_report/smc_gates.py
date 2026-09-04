# -*- coding: utf-8 -*-
"""SMC_GATES - 统一经济准入门槛检查（V633 蓝图固化，防再犯规则 R6/R7）。

所有新本体晋级前必须通过本模块全部检查。任何一项失败 => CLOSED_NO_VARIANTS。
用法: from smc_gates import check_economic_gate; result = check_economic_gate(trades)
"""
import collections


def check_economic_gate(trades, min_n=1000, min_year_n=300, min_month_n=5,
                        wr_min=55.0, avg_min=0.5, pf_min=1.15, payoff_min=0.70,
                        years=("2023", "2024", "2025", "2026")):
    """逐项检查 V633 经济门槛。trades: list of dicts with
    entry_date (YYYYMMDD), net_pnl_pct, reason/exit_reason, symbol.

    Returns dict:
      overall: {...}
      yearly: {year: {...}}
      monthly: {month: n}
      checks: [ {name, pass, detail} ... ]
      gate_pass: bool
    """
    def stats(rows):
        n = len(rows)
        if not n:
            return {"n": 0, "wr": 0.0, "avg": 0.0, "pf": 0.0, "payoff": 0.0}
        wins = [r for r in rows if float(r.get("net_pnl_pct") or 0) > 0]
        losses = [r for r in rows if float(r.get("net_pnl_pct") or 0) <= 0]
        aw = sum(float(r["net_pnl_pct"]) for r in wins) / len(wins) if wins else 0.0
        al = sum(float(r["net_pnl_pct"]) for r in losses) / len(losses) if losses else 0.0
        gp = sum(max(float(r["net_pnl_pct"]), 0) for r in rows)
        gl = abs(sum(min(float(r["net_pnl_pct"]), 0) for r in rows))
        return {
            "n": n,
            "symbols": len({r.get("symbol") for r in rows}),
            "wr": round(100 * len(wins) / n, 4),
            "avg": round(sum(float(r["net_pnl_pct"]) for r in rows) / n, 4),
            "pf": round(gp / gl, 4) if gl else 0.0,
            "payoff": round(abs(aw / al), 4) if al else 0.0,
        }

    overall = stats(trades)
    by_year = collections.defaultdict(list)
    by_month = collections.defaultdict(list)
    for r in trades:
        d = str(r.get("entry_date") or "")
        if len(d) >= 8:
            by_year[d[:4]].append(r)
            by_month[d[:6]].append(r)
    yearly = {y: stats(by_year.get(y, [])) for y in years}
    monthly = {m: len(v) for m, v in sorted(by_month.items()) if m >= "202301"}

    checks = []
    def check(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
        return bool(ok)

    check("total_n", overall["n"] >= min_n, f"n={overall['n']} >= {min_n}")
    check("wr", overall["wr"] >= wr_min, f"WR={overall['wr']}% >= {wr_min}%")
    check("avg_net", overall["avg"] >= avg_min, f"AvgNet={overall['avg']}% >= {avg_min}%")
    check("pf", overall["pf"] >= pf_min, f"PF={overall['pf']} >= {pf_min}")
    check("payoff", overall["payoff"] >= payoff_min, f"payoff={overall['payoff']} >= {payoff_min}")
    check("yearly_n", all(yearly[y]["n"] >= min_year_n for y in years),
          {y: yearly[y]["n"] for y in years})
    check("yearly_avg_positive", all(yearly[y]["avg"] > 0 for y in years),
          {y: yearly[y]["avg"] for y in years})
    zero_months = [m for m, n in monthly.items() if n < min_month_n]
    check("monthly_sample", len(zero_months) == 0, f"months with n<{min_month_n}: {zero_months[:20]}")

    t1_viol = sum(1 for r in trades if r.get("t1_violation"))
    check("t1_zero", t1_viol == 0, f"T+1 violations={t1_viol}")

    gate_pass = all(c["pass"] for c in checks)
    return {"overall": overall, "yearly": yearly, "monthly_counts": monthly,
            "checks": checks, "gate_pass": gate_pass,
            "decision": "PROMOTION_PASS" if gate_pass else "ECONOMIC_GATE_FAIL__CLOSE_ONTOLOGY__NO_VARIANTS"}


if __name__ == "__main__":
    # quick self-test with synthetic data
    import random
    random.seed(1)
    demo = []
    for y in ("2023", "2024", "2025", "2026"):
        for m in range(1, 13):
            for _ in range(30):
                demo.append({"symbol": f"{random.randint(1,1000):06d}.SZ", "entry_date": f"{y}{m:02d}01",
                             "net_pnl_pct": random.gauss(0.8, 4.0), "reason": "TP", "t1_violation": False})
    r = check_economic_gate(demo)
    print("gate_pass:", r["gate_pass"])
    for c in r["checks"]:
        print(f"  {'PASS' if c['pass'] else 'FAIL'} {c['name']}: {c['detail']}")
