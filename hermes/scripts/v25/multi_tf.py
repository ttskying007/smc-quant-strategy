# -*- coding: utf-8 -*-
"""multi_tf.py —— 多周期职责分离工具(审计 §6.1 / Iteration 5).

审计 §6.1 时间框架职责:
  周线  -> 市场方向、主要流动性和大级别状态(仅**已完成**周期)
  日线  -> 核心结构、SSL/BSL、OB/FVG、主信号
  60分钟 -> 结构过渡和入场窗口
  15分钟 -> 只用于执行质量和滑点/涨跌停可成交检查
  上级周期只能使用已完成 K 线; 当前未完成周线不得作为当日方向过滤器.

本模块提供:
  - completed_weekly_only(daily): 仅用已完成周合成(未完成周丢弃)
  - weekly_regime(daily): 周线状态(up/down/neutral), 仅基于已完成周
  - daily_structure_ready(bar): 日线主信号就绪检查(无未来)
  - exec_quality_ok(bar15m, ...): 15分钟执行质量(涨跌停/流动性)
  - role_contract(): 返回职责矩阵(机器可校验, 审计 §5.2 合同思想)
纯内存, 不写生产.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

# 每周交易日数(A 股 5 天)
BARS_PER_WEEK = 5


def iso_week_key(datestr: str) -> Optional[tuple]:
    s = str(datestr or "").split(" ")[0].replace("-", "")
    if len(s) >= 8:
        try:
            d = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
            iso = d.isocalendar()
            return (iso[0], iso[1])
        except Exception:
            return None
    return None


def completed_weekly_only(daily: List[Dict[str, Any]],
                          bars_per_week: int = BARS_PER_WEEK) -> List[Dict[str, Any]]:
    """仅用**已完成**周合成周线(未完成周丢弃, 审计 §6.1/§6.2).

    最后一段不足 bars_per_week 根 => 未完成周, 显式丢弃.
    """
    weeks = {}
    order = []
    for bar in daily:
        key = iso_week_key(bar.get("date") or bar.get("t"))
        if key is None:
            continue
        if key not in weeks:
            weeks[key] = []
            order.append(key)
        weeks[key].append(bar)
    out = []
    for key in order:
        chunk = weeks[key]
        if len(chunk) < bars_per_week:
            continue
        out.append({
            "o": chunk[0]["o"],
            "h": max(b["h"] for b in chunk),
            "l": min(b["l"] for b in chunk),
            "c": chunk[-1]["c"],
            "v": sum(b.get("v", 0) for b in chunk),
            "date": chunk[0].get("date", ""),
        })
    return out


def weekly_regime(daily: List[Dict[str, Any]], lookback: int = 5) -> str:
    """周线状态(up/down/neutral), 仅基于已完成周. 未完成周不参与."""
    w = completed_weekly_only(daily)
    if len(w) < lookback + 1:
        return "neutral"
    recent = w[-lookback:]
    if recent[-1]["c"] > recent[0]["o"]:
        return "up"
    if recent[-1]["c"] < recent[0]["o"]:
        return "down"
    return "neutral"


def daily_signal_ready(bar: Dict[str, Any], confirmed_swing: bool,
                       ob_ready: bool) -> Dict[str, Any]:
    """日线主信号就绪检查: 核心结构已确认 + 无未来信息依赖."""
    return {"ready": confirmed_swing and ob_ready,
            "confirmed_swing": confirmed_swing,
            "ob_ready": ob_ready,
            "bar_date": bar.get("date") or bar.get("t")}


def exec_quality_ok(bar15m: Dict[str, Any], prev_close: float,
                    direction: str, limit_pct: float = 0.10) -> Dict[str, Any]:
    """15分钟执行质量检查(仅用于执行, 不参与信号): 涨跌停可成交性 + 流动性."""
    o = bar15m.get("o", 0)
    v = bar15m.get("v", 0)
    if o <= 0 or v <= 0:
        return {"ok": False, "reason": "NO_LIQUIDITY"}
    if direction == "bull" and o >= prev_close * (1 + limit_pct):
        return {"ok": False, "reason": "LIMIT_UP"}
    if direction == "bear" and o <= prev_close * (1 - limit_pct):
        return {"ok": False, "reason": "LIMIT_DOWN"}
    return {"ok": True, "reason": "OK"}


def role_contract() -> Dict[str, str]:
    """多周期职责合同(机器可校验, 审计 §5.2 思想)."""
    return {
        "weekly": "MARKET_DIRECTION_ONLY_COMPLETED_BARS",
        "daily": "CORE_STRUCTURE_SIGNAL",
        "m60": "STRUCTURE_TRANSITION_ENTRY_WINDOW",
        "m15": "EXECUTION_QUALITY_ONLY",
        "rule": "HIGHER_TF_USES_COMPLETED_BARS_ONLY",
    }