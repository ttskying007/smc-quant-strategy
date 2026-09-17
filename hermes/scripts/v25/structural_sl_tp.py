# -*- coding: utf-8 -*-
"""structural_sl_tp.py —— 结构优先 SL/TP 生成器(审计 §7.2/§7.3 / Iteration 1).

审计 §7.2 止损优先级:
  ① 造成 sweep 的结构失败位, 加预注册 buffer
  ② 入场前已确认的 OB/FVG 下沿
  ③ 入场前 swing low/high
  ④ 固定 ATR fallback, 但必须**单独统计 fallback 比例**
  任何 SL 都必须保存 source_event_id、visible_at 和距离分布。

审计 §7.3 止盈:
  TP 只能使用**入场前可见且未消费**的结构, 或者预注册的 R 倍数。
  不得从入场后的 swing/未来高点/未来 FVG/未来 CHOCH 反推 TP。

本模块:
  - structural_stop(bars, sweep_idx, ...): 结构失败位(SL) —— sweep bar 低点
    * 0.99(结构失败 buffer, 与 V699 STOP_BUFFER 一致)
  - visible_swing_high_target(bars, sweep_idx, entry): 入场前可见且未消费的
    swing high(TP) —— 与 V699 visible_target 同语义(未被消费检查)
  - decide_sl_tp(...): 结构优先 + fallback(ATR/R 倍数), 统计 fallback 比例
  - SL/TP 均携带 source(STRUCTURE/ATR_FALLBACK/R_FALLBACK) + 证据(visible_at)
纯内存, 不写生产。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

SWING_LEFT = 3
SWING_RIGHT = 3
STOP_BUFFER = 0.99  # 结构失败位 buffer(V699 一致)
SWEEP_PCT = 0.003


def is_swing_high(bars: List[Dict[str, Any]], j: int) -> bool:
    """右侧确认完成的 swing high(§7.3: 入场前可见结构)."""
    if j < SWING_LEFT or j + SWING_RIGHT >= len(bars):
        return False
    h = bars[j]["h"]
    left = [bars[k]["h"] for k in range(j - SWING_LEFT, j)]
    right = [bars[k]["h"] for k in range(j + 1, j + SWING_RIGHT + 1)]
    return h > max(left) and h >= max(right)


def structural_stop(bars: List[Dict[str, Any]], sweep_idx: int) -> Dict[str, Any]:
    """SL 优先级①: 造成 sweep 的结构失败位 = sweep bar 低点 * buffer.

    返回含 source=STRUCTURE / sweep_idx / sweep_low / stop。
    """
    sweep_low = bars[sweep_idx]["l"]
    return {"source": "STRUCTURE", "stop": round(sweep_low * STOP_BUFFER, 6),
            "sweep_idx": sweep_idx, "sweep_low": round(sweep_low, 6),
            "visible_at": sweep_idx}


def visible_swing_high_target(bars: List[Dict[str, Any]], sweep_idx: int,
                              entry: float) -> Optional[Dict[str, Any]]:
    """TP: 入场前可见**且未消费**的 swing high(§7.3).

    未被消费: sweep 低点 > swing high(未被穿透); 且高过 entry。
    与 V699 visible_target 同语义(审计 §3.7 修复后)。
    """
    sweep_low = bars[sweep_idx]["l"]
    candidates = []
    # 从 sweep 前一根往回找入场前可见的 swing high(最近的优先)
    for j in range(sweep_idx - 1, SWING_LEFT - 1, -1):
        if is_swing_high(bars, j) and bars[j]["h"] > entry:
            # 未消费: swing high 形成后至 sweep 前, 无 bar 高点重新触及
            # (被再次触碰的流动性已供给, 不能作目标; §7.3/§3.7 语义)
            if not any(bars[k]["h"] >= bars[j]["h"]
                       for k in range(j + SWING_RIGHT + 1, sweep_idx)):
                candidates.append(j)
    if not candidates:
        return None
    j = candidates[0]  # 最近者
    return {"source": "STRUCTURE", "target": round(bars[j]["h"], 6),
            "swing_idx": j, "visible_at": j + SWING_RIGHT,
            "swing_date": bars[j].get("date") or bars[j].get("t")}


def atr_fallback_sl(bars: List[Dict[str, Any]], entry: float, idx: int,
                    atr_mult: float = 1.5) -> float:
    """SL fallback: ATR 倍数(§7.2 优先级④, 必须统计 fallback 比例)."""
    if idx < 15:
        return round(entry * 0.95, 6)
    trs = []
    for k in range(idx - 14, idx):
        trs.append(max(bars[k]["h"] - bars[k]["l"],
                       abs(bars[k]["h"] - bars[k - 1]["c"]),
                       abs(bars[k]["l"] - bars[k - 1]["c"])))
    atr = sum(trs) / len(trs)
    return round(entry - atr_mult * atr, 6)


def r_fallback_tp(entry: float, stop: float, r_mult: float = 2.0) -> float:
    """TP fallback: 预注册 R 倍数(§7.3)."""
    return round(entry * (1 + r_mult * (entry - stop) / entry), 6)


class SLTPGenerator:
    """结构优先 SL/TP 生成器, 统计 fallback 比例(§7.2/§7.3)."""

    def __init__(self, atr_mult: float = 1.5, r_mult: float = 2.0,
                 use_structure: bool = True) -> None:
        self.atr_mult = atr_mult
        self.r_mult = r_mult
        self.use_structure = use_structure
        self.sl_fallback_count = 0
        self.tp_fallback_count = 0
        self.total = 0

    def decide(self, bars: List[Dict[str, Any]], sweep_idx: int,
               entry_idx: int, entry: float) -> Dict[str, Any]:
        """生成 SL/TP: 结构优先, ATR/R fallback, 记录 fallback 比例."""
        self.total += 1
        # SL: 结构失败位优先(§7.2 ①), ATR fallback(④)
        sl = None
        if self.use_structure and 0 <= sweep_idx < len(bars):
            ss = structural_stop(bars, sweep_idx)
            if ss["stop"] < entry:
                sl = ss
        if sl is None:
            sl = {"source": "ATR_FALLBACK",
                  "stop": atr_fallback_sl(bars, entry, entry_idx, self.atr_mult)}
            self.sl_fallback_count += 1
        # TP: 入场前可见未消费结构优先(§7.3), R 倍数 fallback
        tp = None
        if self.use_structure:
            vt = visible_swing_high_target(bars, sweep_idx, entry)
            if vt is not None:
                tp = vt
        if tp is None:
            tp = {"source": "R_FALLBACK",
                  "target": r_fallback_tp(entry, sl["stop"], self.r_mult)}
            self.tp_fallback_count += 1
        return {"sl": sl, "tp": tp, "entry": entry,
                "sl_fallback_ratio": (self.sl_fallback_count / self.total
                                      if self.total else 0.0),
                "tp_fallback_ratio": (self.tp_fallback_count / self.total
                                      if self.total else 0.0)}