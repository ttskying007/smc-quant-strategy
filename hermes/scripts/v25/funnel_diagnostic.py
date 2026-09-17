# -*- coding: utf-8 -*-
"""funnel_diagnostic.py —— 选股漏斗分层诊断工具(审计 §8.1/§8.2).

审计 §8.1: "当前漏斗不应只看最终数量。每一层必须输出: 进入数量、通过数量、
通过率、因拒绝原因分组的数量、按股票/年份/市场阶段和行业的分布。"
审计 §8.2: "如果候选长期为零, 应先回答是哪一层为零:
  ① 数据未刷新  ② swing 尚未完成确认  ③ sweep 发生但未 reclaim
  ④ response 未突破  ⑤ 没有入场前可见的结构目标  ⑥ 研究 gate 未通过
  ⑦ 次日开盘不在结构范围内
  只有前五层反复为零时, 才是信号设计过严; 第六层为零可能是经济门槛正确
  生效; 第七层为零则是可成交性过滤。"

本模块:
  - STAGES: 漏斗 7 层(§8.2 顺序)
  - report(stage_counts, reject_by_reason): 分层诊断报告(通过率/拒绝原因分组)
  - stage_breakdown(candidates_by_stage): 按股票/年份/市场阶段分布
  - diagnose_zero(funnel): 候选长期为零 -> 定位为零的层(§8.2 语义解释)
纯内存, 不写生产。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List

# §8.2 漏斗 7 层
STAGES = [
    ("1_data_fresh", "数据已刷新(最新K线==市场日)"),
    ("2_swing_confirmed", "swing 右侧确认完成"),
    ("3_sweep_reclaim", "sweep 发生且收盘回收"),
    ("4_response_break", "response 收盘突破 sweep 高"),
    ("5_visible_target", "存在入场前可见的结构目标"),
    ("6_research_gate", "研究 gate 通过(§10.3)"),
    ("7_open_in_range", "次日开盘在结构范围内(可成交)"),
]


def report(stage_counts: Dict[str, int],
           reject_by_reason: Dict[str, int]) -> Dict[str, Any]:
    """分层诊断: 每层进入/通过/通过率 + 拒绝原因分组.

    stage_counts: {stage_key: 进入该层数量}(递减, 最终层=候选数)
    reject_by_reason: {reason: count}(§8.1 按拒绝原因分组)
    """
    rows = []
    prev = None
    for key, label in STAGES:
        entered = stage_counts.get(key, 0)
        passed = stage_counts.get(STAGES[STAGES.index((key, label)) + 1][0]
                                  if STAGES.index((key, label)) + 1 < len(STAGES)
                                  else None, 0)
        rate = (100.0 * passed / entered) if entered else 0.0
        rows.append({"stage": key, "label": label, "entered": entered,
                     "passed": passed if passed is not None else entered,
                     "pass_rate_pct": round(rate, 2)})
        prev = entered
    return {"stages": rows, "reject_by_reason": dict(reject_by_reason),
            "n_final": stage_counts.get("7_open_in_range", 0)}


def stage_breakdown(candidates_by_stage: Dict[str, List[Dict[str, Any]]],
                    dim: str = "year") -> Dict[str, Dict[str, int]]:
    """按维度(股票/年份/市场阶段)统计各层分布(§8.1).

    candidates_by_stage: {stage_key: [{symbol, year, market_phase, ...}]}
    dim: 'symbol' | 'year' | 'market_phase'
    """
    out = defaultdict(Counter)
    for stage, items in candidates_by_stage.items():
        for it in items:
            key = it.get(dim, "unknown")
            out[stage][key] += 1
    return {k: dict(v) for k, v in out.items()}


def diagnose_zero(funnel: Dict[str, int],
                  n_candidates: int = 0) -> Dict[str, Any]:
    """候选长期为零 -> 定位为零的层(§8.2 语义解释).

    funnel: {stage_key: 进入数量}
    返回第一个为零的层及其 §8.2 语义解释。
    """
    for key, label in STAGES:
        if funnel.get(key, 0) == 0:
            reason_map = {
                "1_data_fresh": "数据未刷新(需检查数据管线)",
                "2_swing_confirmed": "swing 尚未完成确认(信号设计或窗口过严)",
                "3_sweep_reclaim": "sweep 发生但未 reclaim(形态条件)",
                "4_response_break": "response 未突破(形态条件)",
                "5_visible_target": "没有入场前可见的结构目标(目标定义过严)",
                "6_research_gate": "研究 gate 未通过(经济门槛正确生效, 非缺陷)",
                "7_open_in_range": "次日开盘不在结构范围内(可成交性过滤)",
            }
            return {"zero_stage": key, "label": label,
                    "explanation": reason_map[key],
                    "is_gate_ok": key == "6_research_gate",
                    "is_exec_filter": key == "7_open_in_range",
                    "note": ("仅前五层反复为零才是信号设计过严; 第六层为零是"
                             "经济门槛正确生效; 第七层为零是可成交性过滤(§8.2)")}
    return {"zero_stage": None,
            "explanation": "漏斗各层均有进入量, 但最终候选为 0(需查拒绝原因)",
            "note": "检查 reject_by_reason 定位具体拒绝原因(§8.1)"}