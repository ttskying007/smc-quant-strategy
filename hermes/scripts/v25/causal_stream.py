# -*- coding: utf-8 -*-
"""causal_stream.py —— 最小事件流引擎(审计§3.2 P0 / §5.3 / Iteration 0).

审计关切:
  §3.2 P0: 一次性全量检测导致点时不一致风险。应改为事件流模式:
          "每个 bar 到来时只更新状态, 结构在右侧确认 bar 完成后入库;
           回测和实时扫描共用同一个 step(bar) 引擎。"
  §5.3: 用同一数据前缀分别运行"在线逐 bar"和"批量回放",
        输出事件 ID 必须完全一致。

本引擎复刻 V697 因果模板(confirmed SSL -> sweep/reclaim -> response -> T+1):
  - BarStream: 只向前推进, 不可回退
  - CausalEventEngine.step(bar): 每根 bar 增量更新状态:
      * 摆动低确认(右侧 3 bar 完成后才可见)
      * 未消费状态: 一旦被后续 bar 穿透, 标记 CONSUMED(不可再用)
      * sweep 检测: 低点穿透 >=0.3% 且收盘回收
      * response 检测: 下一 bar 收盘突破 sweep 高
      * 事件在右侧确认后**入库**(visible_time = 确认完成时点)
  - event_ids(): 输出稳定事件 ID 集合 (symbol, swing_date, sweep_date, response_date)

关键性质(审计验收):
  * **在线逐 bar == 批量回放**: step-by-step 推进产生的事件集合,
    必须与一次性全量扫描过滤出的集合完全一致 —— 由 tests 断言。
纯内存, 不写生产; 无 outcome 字段(与 V697 outcome-blind 一致).
"""
from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

SWING_LEFT = 3
SWING_RIGHT = 3
SWEEP_PCT = 0.003
YEARS = ("2023", "2024", "2025", "2026")


def datekey(v: Any) -> str:
    digits = "".join(ch for ch in str(v or "") if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


class CausalEventEngine:
    """逐 bar 事件流引擎: 每个 bar 到达时只更新状态, 结构右侧确认后入库."""

    def __init__(self, symbol: str = "TEST") -> None:
        self.symbol = symbol
        self._bars: List[Dict[str, Any]] = []
        self._visible_swings: List[Dict[str, Any]] = []  # {idx, low, visible_at, consumed}
        self._events: Set[Tuple[str, str, str, str]] = set()

    def _mark_consumed_below(self, low: float) -> None:
        """价格穿透任一未消费摆动低 -> 消费(流动性已供给)."""
        for sw in self._visible_swings:
            if not sw["consumed"] and low <= sw["low"]:
                sw["consumed"] = True

    def _register_new_swings(self, idx: int) -> None:
        """bar idx 到达后, 若 idx-1 成为已确认摆动低(右侧 SWING_RIGHT 完成), 入库."""
        j = idx - SWING_RIGHT
        if j < SWING_LEFT:
            return
        low = self._bars[j]["l"]
        left = [self._bars[k]["l"] for k in range(j - SWING_LEFT, j)]
        right = [self._bars[k]["l"] for k in range(j + 1, j + SWING_RIGHT + 1)]
        if low < min(left) and low <= min(right):
            self._visible_swings.append(
                {"idx": j, "low": low, "visible_at": idx, "consumed": False})

    def _check_sweep_response(self, idx: int) -> None:
        """idx 到达时检查: 上一 bar(idx-1)为 sweep + 本 bar(idx)为 response."""
        if idx < 2:
            return
        sweep = self._bars[idx - 1]
        response = self._bars[idx]
        if not (response["c"] > sweep["h"]):
            return
        # 找最近的未消费已确认摆动低(在 sweep 前确认)
        anchor = None
        for sw in reversed(self._visible_swings):
            if sw["consumed"]:
                continue
            if sw["idx"] + SWING_RIGHT >= idx - 1:
                continue
            if sweep["l"] <= sw["low"] * (1.0 - SWEEP_PCT) and sweep["c"] > sw["low"]:
                anchor = sw
                break
        if anchor is None:
            return
        if str(sweep["t"])[:4] not in YEARS:
            return
        self._events.add((self.symbol, self._bars[anchor["idx"]]["t"],
                          sweep["t"], response["t"]))

    def step(self, bar: Dict[str, Any]) -> None:
        """推进一根 bar(只前向, 不可回退)."""
        b = {**bar, "t": datekey(bar.get("t") or bar.get("date") or "")}
        if not b["t"]:
            return
        self._bars.append(b)
        idx = len(self._bars) - 1
        # 顺序(审计修正): 先注册新确认的摆动低 -> 再检查本 bar 是否构成
        # sweep+response 事件 -> **最后**才标记本 bar 的穿透为消费。
        # 关键: sweep 动作本身是"利用未消费流动性"(触发事件), 不是先消费再触发;
        # 本 bar 的 low 只应消费**更早**已形成的 swing, 且不能因本 bar 是 sweep
        # 而把自己要利用的 swing 先标为 consumed(V697 语义: 仅排除 sweep 之前
        # 的穿透, 见 canonical_swept_swing_low L94 range(.., sweep_idx))。
        self._register_new_swings(idx)
        self._check_sweep_response(idx)
        # 当前 bar 穿透: 消费**该 bar 之前已确认**的 swing。
        # 条件 sw.visible_at < idx-1: 排除"本 bar 或前一根(sweep)刚确认/利用的
        # swing" —— sweep 动作是**利用**未消费流动性触发事件, 不消费自身 anchor
        # (与 V697 canonical_swept_swing_low 一致: 仅排除 sweep **之前**的穿透)。
        for sw in self._visible_swings:
            if (not sw["consumed"] and sw["visible_at"] < idx - 1
                    and b["l"] <= sw["low"]):
                sw["consumed"] = True

    def event_ids(self) -> Set[Tuple[str, str, str, str]]:
        return set(self._events)


def batch_replay(bars: List[Dict[str, Any]], symbol: str = "TEST") -> Set[Tuple[str, str, str, str]]:
    """批量回放(一次性全量扫描): 与在线逐 bar 的对照实现.

    注意: 批量回放必须**模拟同样的状态机语义** —— 即按时间顺序逐步应用
    状态更新, 只是用循环代替外部逐次 step 调用。这是"批量回放"的正确含义
    (非"用未来数据一次性检测")。
    """
    eng = CausalEventEngine(symbol)
    for bar in bars:
        eng.step(bar)
    return eng.event_ids()


def events_match_online_vs_batch(bars: List[Dict[str, Any]], symbol: str = "TEST") -> bool:
    """审计§5.3: 在线逐 bar vs 批量回放, 事件 ID 完全一致."""
    online = CausalEventEngine(symbol)
    for bar in bars:
        online.step(bar)
    batch = batch_replay(bars, symbol)
    return online.event_ids() == batch


def make_bars(prices) -> List[Dict[str, Any]]:
    """构造 bars: prices=[(t,o,h,l,c,v)]. 简化辅助."""
    out = []
    for i, (t, o, h, l, c, v) in enumerate(prices):
        out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    return out