# -*- coding: utf-8 -*-
"""fvg_ob_events.py —— FVG / OB 事件检测器(审计 §4.2/§4.3).

审计 §4.2 FVG:
  - Bullish FVG: 第一根高点 < 第三根低点; Bearish: 第一根低点 > 第三根高点
  - 第三根收盘后才可见(visible_at = i+2)
  - 最小宽度按历史波动率归一化, 但波动率只能来自**形成前**的滚动窗口
  - 完全填补 -> MITIGATED; 收盘穿越 -> INVALIDATED
  - 不允许把未来填补结果用于形成时的质量分数

审计 §4.3 OB:
  - 不是"某根反向 K 线": 强制包含上下文结构突破(BOS/CHOCH displacement 证据)
  - 区域形成时间和可见时间
  - 第一次回测 / 重复回测 / 失效穿越次数
  - 进入区域时的成交量/波动状态仅作为当时可见的诊断字段

本模块(纯内存, 无 IO):
  - detect_fvgs(bars, atr_window): 逐 bar 检测 FVG(仅形成前窗口的 ATR)
  - FvgTracker: 状态机(ACTIVE -> MITIGATED/INVALIDATED), 逐 bar 推进
  - detect_obs(bars, disp_pct, ctx_lookback): 检测含 BOS 证据的 OB
  - 事件均携带 event_id/type/direction/formed_at/visible_at/price_zone/state
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

MIN_GAP_ATR = 0.5   # FVG 最小宽度 = 0.5 * ATR(形成前窗口)
DISP_PCT = 0.02     # OB displacement 最小实体 2%
CTX_LOOKBACK = 5    # BOS 上下文: displacement 收盘突破前 N 根高点


def _atr(bars: List[Dict[str, Any]], end: int, window: int = 14) -> float:
    """ATR(仅用 bars[:end+1] 形成前窗口, 无未来)."""
    if end < 2:
        return 0.0
    trs = []
    for k in range(max(0, end - window + 1), end):
        trs.append(max(bars[k]["h"] - bars[k]["l"],
                       abs(bars[k]["h"] - bars[k - 1]["c"]),
                       abs(bars[k]["l"] - bars[k - 1]["c"])))
    return sum(trs) / len(trs) if trs else 0.0


def detect_fvgs(bars: List[Dict[str, Any]],
                min_gap_atr: float = MIN_GAP_ATR) -> List[Dict[str, Any]]:
    """逐 bar 检测 FVG(三根 bar 序列, 第三根收盘后可见).

    返回事件列表: {event_id, type, direction, formed_at, visible_at,
                   upper, lower, price_zone, gap_pct, state: ACTIVE}
    """
    events = []
    for i in range(len(bars) - 2):
        b1, b2, b3 = bars[i], bars[i + 1], bars[i + 2]
        atr = _atr(bars, i)  # 形成前窗口(无未来)
        if atr <= 0:
            continue
        # Bullish FVG: b1.h < b3.l
        if b1["h"] < b3["l"]:
            gap = b3["l"] - b1["h"]
            if gap >= min_gap_atr * atr:
                events.append({
                    "event_id": "FVG_BULL_%d" % (i + 2),
                    "type": "FVG", "direction": "bull",
                    "formed_at": i, "visible_at": i + 2,
                    "upper": b3["l"], "lower": b1["h"],
                    "price_zone": (b1["h"], b3["l"]),
                    "gap_pct": round(100 * gap / b1["c"], 4),
                    "state": "ACTIVE",
                })
        # Bearish FVG: b1.l > b3.h
        if b1["l"] > b3["h"]:
            gap = b1["l"] - b3["h"]
            if gap >= min_gap_atr * atr:
                events.append({
                    "event_id": "FVG_BEAR_%d" % (i + 2),
                    "type": "FVG", "direction": "bear",
                    "formed_at": i, "visible_at": i + 2,
                    "upper": b1["l"], "lower": b3["h"],
                    "price_zone": (b3["h"], b1["l"]),
                    "gap_pct": round(100 * gap / b1["c"], 4),
                    "state": "ACTIVE",
                })
    return events


class FvgTracker:
    """FVG 状态机: ACTIVE -> MITIGATED(完全填补) / INVALIDATED(收盘穿越).

    逐 bar 推进(仅可见事件进入状态机; 未来填补不用于形成时质量分数).
    """

    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self.events = {e["event_id"]: dict(e) for e in events}

    def step(self, bar: Dict[str, Any], idx: int) -> None:
        for eid, e in self.events.items():
            if e["state"] != "ACTIVE" or idx < e["visible_at"]:
                continue
            if e["direction"] == "bull":
                # 完全填补: 低点 <= 下沿
                if bar["l"] <= e["lower"]:
                    e["state"] = "MITIGATED"
                    e["mitigated_at"] = idx
                # 收盘穿越: 收盘 < 下沿
                elif bar["c"] < e["lower"]:
                    e["state"] = "INVALIDATED"
                    e["invalidated_at"] = idx
            else:
                if bar["h"] >= e["upper"]:
                    e["state"] = "MITIGATED"
                    e["mitigated_at"] = idx
                elif bar["c"] > e["upper"]:
                    e["state"] = "INVALIDATED"
                    e["invalidated_at"] = idx

    def states(self) -> Dict[str, str]:
        return {eid: e["state"] for eid, e in self.events.items()}


def detect_obs(bars: List[Dict[str, Any]],
               disp_pct: float = DISP_PCT,
               ctx_lookback: int = CTX_LOOKBACK) -> List[Dict[str, Any]]:
    """检测含 BOS 证据的 OB(审计 §4.3).

    displacement bar: 实体 >= disp_pct 且收盘突破前 ctx_lookback 根高点
    (bullish) / 低点 (bearish) —— BOS/CHOCH 结构证据。
    区域 = displacement bar 的 [open, high](bullish 需求区) / [low, open]
    (bearish 供给区)。
    诊断字段(仅当时可见): 该 bar 成交量/波动。
    """
    obs = []
    for i in range(ctx_lookback, len(bars)):
        b = bars[i]
        body = abs(b["c"] - b["o"])
        if body <= 0 or body / b["o"] < disp_pct:
            continue
        if b["c"] > b["o"]:  # bullish displacement
            hi_before = max(bars[k]["h"] for k in range(i - ctx_lookback, i))
            if b["c"] > hi_before:  # BOS 证据: 收盘突破前高
                obs.append({
                    "event_id": "OB_BULL_%d" % i,
                    "type": "OB", "direction": "bull",
                    "formed_at": i, "visible_at": i,
                    "region": (b["o"], b["h"]),
                    "bos_evidence": {"break_above": hi_before,
                                     "ctx_lookback": ctx_lookback},
                    "displacement_pct": round(100 * body / b["o"], 4),
                    "volume": b.get("v", 0),
                    "state": "ACTIVE",
                    "tests": 0, "invalidations": 0,
                })
        else:  # bearish displacement
            lo_before = min(bars[k]["l"] for k in range(i - ctx_lookback, i))
            if b["c"] < lo_before:  # CHOCH/BOS 证据: 收盘跌破前低
                obs.append({
                    "event_id": "OB_BEAR_%d" % i,
                    "type": "OB", "direction": "bear",
                    "formed_at": i, "visible_at": i,
                    "region": (b["l"], b["o"]),
                    "bos_evidence": {"break_below": lo_before,
                                     "ctx_lookback": ctx_lookback},
                    "displacement_pct": round(100 * body / b["o"], 4),
                    "volume": b.get("v", 0),
                    "state": "ACTIVE",
                    "tests": 0, "invalidations": 0,
                })
    return obs


class ObTracker:
    """OB 状态机: 记录第一次回测/重复回测/失效穿越次数(§4.3)."""

    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self.events = {e["event_id"]: dict(e) for e in events}

    def step(self, bar: Dict[str, Any], idx: int) -> None:
        for eid, e in self.events.items():
            if e["state"] != "ACTIVE" or idx < e["visible_at"]:
                continue
            lo, hi = e["region"]
            if e["direction"] == "bull":
                # 回测: 低点进入区域
                if bar["l"] <= hi:
                    e["tests"] += 1
                # 失效穿越: 收盘跌破区域下沿
                if bar["c"] < lo:
                    e["state"] = "INVALIDATED"
                    e["invalidated_at"] = idx
                    e["invalidations"] += 1
            else:
                if bar["h"] >= lo:
                    e["tests"] += 1
                if bar["c"] > hi:
                    e["state"] = "INVALIDATED"
                    e["invalidated_at"] = idx
                    e["invalidations"] += 1

    def states(self) -> Dict[str, Dict[str, Any]]:
        return {eid: {"state": e["state"], "tests": e["tests"],
                      "invalidations": e["invalidations"]}
                for eid, e in self.events.items()}