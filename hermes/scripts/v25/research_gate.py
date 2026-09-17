# -*- coding: utf-8 -*-
"""research_gate.py —— 预注册研究门槛评估器(审计 §10.3 / Iteration 3).

审计 §10.3: "建议把门槛固定在代码中, 而不是写在文档里":

  指标          最低要求
  总交易数       1000
  每年交易数     300
  每年净收益     > 0
  总 WR          >= 55%
  平均净收益      >= 0.5%
  PF             >= 1.15
  Payoff         >= 0.70
  月度交易数     严格按完整区间检查, 不能隐藏零交易月
  T+1 违规       0
  前视检查       0
  oracle 差异    0

"这些是许可门槛, 不是优化目标。若策略只有在放宽门槛后才'可用',
 应归类为研究失败, 而不是生产策略。"

本模块:
  - GATE: 预注册门槛(常量, 不可在运行时放宽)
  - evaluate(ledger): 给定交易台账(dict 列表, 含 entry_date/net_pnl_pct/
    gross_pnl_pct), 输出逐年/逐月/总体是否达标 + 完整诊断
  - monthly_span_check: 完整区间含零交易月(不能隐藏)
纯内存, 不写生产。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List

# 预注册门槛(审计 §10.3; 许可门槛, 非优化目标)
GATE = {
    "n_min": 1000,
    "yearly_n_min": 300,
    "yearly_avg_net_min_exclusive": 0.0,
    "wr_min": 55.0,
    "avg_net_pnl_pct_min": 0.5,
    "pf_min": 1.15,
    "payoff_min": 0.70,
    "monthly_trade_count_min_exclusive": 4,  # 完整区间内每月 >= 5
    "t1_violations_max": 0,
    "lookahead_max": 0,
    "oracle_diff_max": 0,
}


def _pct_metrics(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """从台账计算总体指标(W/R, 平均净收益, PF, Payoff)."""
    if not rows:
        return {"n": 0, "wr": 0.0, "avg_net": 0.0, "pf": 0.0, "payoff": 0.0}
    nets = [r.get("net_pnl_pct", 0.0) for r in rows]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    gross = sum(wins)
    loss_abs = abs(sum(losses))
    wr = 100.0 * len(wins) / len(rows)
    avg = sum(nets) / len(rows)
    pf = gross / loss_abs if loss_abs else 0.0
    payoff = ((sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
              if wins and losses else 0.0)
    return {"n": len(rows), "wr": wr, "avg_net": avg, "pf": pf,
            "payoff": payoff}


def _ym(d: str) -> str:
    """日期 -> YYYYMM(容忍 -/ 分隔)."""
    return "".join(c for c in str(d) if c.isdigit())[:6]


def monthly_span(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """完整区间月度交易数(含零交易月, 不能隐藏).

    起止 = 首/末交易的 YYYYMM; 区间内每月计数(0 也列出).
    """
    months = Counter(_ym(r.get("entry_date", "")) for r in rows)
    months.pop("", None)
    if not months:
        return {}
    start, end = min(months), max(months)
    out = {}
    y, m = int(start[:4]), int(start[4:6])
    while f"{y:04d}{m:02d}" <= end:
        out[f"{y:04d}{m:02d}"] = months.get(f"{y:04d}{m:02d}", 0)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def evaluate(ledger: List[Dict[str, Any]],
             t1_violations: int = 0, lookahead: int = 0,
             oracle_diff: int = 0,
             gate: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """门槛评估. 返回 {passed, checks: {name: {ok, value, min}}, diagnostics}.

    ledger: 交易台账(需含 entry_date / net_pnl_pct; 可选 gross_pnl_pct)
    """
    g = gate or GATE
    rows = [r for r in ledger if r.get("entry_date")]
    metrics = _pct_metrics(rows)
    yearly = defaultdict(list)
    for r in rows:
        yearly[_ym(r["entry_date"])[:4]].append(r)

    checks = {}

    def _c(name, ok, value, minimum):
        checks[name] = {"ok": bool(ok), "value": value, "min": minimum}

    _c("total_n", metrics["n"] >= g["n_min"], metrics["n"], g["n_min"])
    _c("wr", metrics["wr"] >= g["wr_min"], round(metrics["wr"], 2), g["wr_min"])
    _c("avg_net", metrics["avg_net"] >= g["avg_net_pnl_pct_min"],
       round(metrics["avg_net"], 4), g["avg_net_pnl_pct_min"])
    _c("pf", metrics["pf"] >= g["pf_min"], round(metrics["pf"], 4), g["pf_min"])
    _c("payoff", metrics["payoff"] >= g["payoff_min"],
       round(metrics["payoff"], 4), g["payoff_min"])
    _c("t1_violations", t1_violations <= g["t1_violations_max"],
       t1_violations, g["t1_violations_max"])
    _c("lookahead", lookahead <= g["lookahead_max"], lookahead,
       g["lookahead_max"])
    _c("oracle_diff", oracle_diff <= g["oracle_diff_max"], oracle_diff,
       g["oracle_diff_max"])

    # 逐年
    year_checks = {}
    for y in sorted(yearly):
        ym = _pct_metrics(yearly[y])
        avg_ok = ym["avg_net"] > g["yearly_avg_net_min_exclusive"]
        n_ok = ym["n"] >= g["yearly_n_min"]
        year_checks[y] = {
            "n": ym["n"], "n_ok": n_ok,
            "avg_net": round(ym["avg_net"], 4), "avg_ok": avg_ok,
            "wr": round(ym["wr"], 2),
            "ok": n_ok and avg_ok,
        }
        _c("yearly_%s_n" % y, n_ok, ym["n"], g["yearly_n_min"])
        _c("yearly_%s_avg_net" % y, avg_ok, round(ym["avg_net"], 4),
           g["yearly_avg_net_min_exclusive"])

    # 月度完整区间(含零交易月)
    span = monthly_span(rows)
    bad_months = [m for m, n in span.items()
                  if n <= g["monthly_trade_count_min_exclusive"]]
    _c("monthly_span", len(bad_months) == 0, {"zero_or_low": bad_months},
       g["monthly_trade_count_min_exclusive"] + 1)

    passed = all(c["ok"] for c in checks.values())
    return {"passed": passed, "checks": checks, "yearly": year_checks,
            "monthly_span": span, "n_trades": metrics["n"],
            "note": "许可门槛, 非优化目标; 放宽门槛后的'可用'归类为研究失败"}