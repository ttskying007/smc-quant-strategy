# -*- coding: utf-8 -*-
"""core/mss.py —— V2 Structure Engine 2.0: 结构转移精确语义
蓝图 §7: MSS/CHOCH/BOS 必须统一, 且区分:
  - 结构点: 确认 swing high/low(PIVOT_R 窗口, 无前视)
  - CHOCH(Change of Character): 逆趋势方向突破最近确认 swing —— 趋势可能反转的第一证据
  - MSS  (Market Structure Shift): 与 CHOCH 同类(趋势反转的第一腿), 本项目与 CHOCH 合并语义分级
  - BOS  (Break of Structure): 顺趋势方向突破最近确认 swing —— 趋势延续证据

语义规则(决策时点 i 可得, 无前视):
  1. swing 确认需 PIVOT_R 根后续 bar → 突破判定只能用'已确认 swing'
  2. 突破 = close 突破 swing 价(实体突破, 非影线)
  3. 趋势上下文 = 突破前 20 根的方向序列(更高高/更低低计数)
  4. 记录: {type, level, break_idx, trend_before, strength}
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low

PIVOT_R = 3


def confirmed_swings(daily, i, lookback=90):
    """返回 i 之前已确认的 swing(结构点)。确认条件: j±PIVOT_R 均在 i 之前(无前视)。"""
    lb0 = max(0, i - lookback)
    highs, lows = [], []
    for j in range(lb0 + PIVOT_R, i - PIVOT_R):
        if is_swing_high(daily, j):
            highs.append({"idx": j, "price": daily[j]["h"]})
        if is_swing_low(daily, j):
            lows.append({"idx": j, "price": daily[j]["l"]})
    return highs, lows


def trend_before(daily, i, n=20):
    """突破前的趋势上下文: +1(上行结构) / -1(下行结构) / 0(横盘)。更高高更高低计数。"""
    w = daily[max(0, i - n):i]
    if len(w) < 8:
        return 0
    hh = sum(1 for k in range(1, len(w)) if w[k]["h"] > w[k - 1]["h"])
    ll = sum(1 for k in range(1, len(w)) if w[k]["l"] < w[k - 1]["l"])
    return 1 if hh > ll * 1.3 else (-1 if ll > hh * 1.3 else 0)


def structure_shift(daily, i, lookback=90):
    """判定 daily[i] 是否发生结构转移(CHOCH/MSS)或延续(BOS)。
    返回 None 或 {type: 'CHOCH'|'BOS', direction, level, break_idx, trend_before, strength}。"""
    if i < 25:
        return None
    highs, lows = confirmed_swings(daily, i, lookback)
    if not highs and not lows:
        return None
    b = daily[i]
    c = b["c"]
    tr = trend_before(daily, i)
    # 上破: close 突破最近确认 swing high
    if highs:
        last_h = max(highs, key=lambda s: s["idx"])  # 最近的高结构点
        if last_h["idx"] < i - 1 and c > last_h["price"]:
            # 趋势非上行时上破 = CHOCH(反转信号); 上行趋势上破 = BOS(延续)
            typ = "BOS" if tr >= 0 else "CHOCH"
            # strength: 突破幅度相对 ATR
            import core.structure as ST
            atr = ST.atr_of(daily, i - 1) or (last_h["price"] * 0.02)
            mag = (c - last_h["price"]) / atr if atr else 0
            return {"type": typ, "direction": "LONG", "level": last_h["price"],
                    "break_idx": i, "trend_before": tr,
                    "strength": round(min(100.0, 50 + mag * 25), 1)}
    # 下破: close 突破最近确认 swing low
    if lows:
        last_l = max(lows, key=lambda s: s["idx"])
        if last_l["idx"] < i - 1 and c < last_l["price"]:
            typ = "BOS" if tr <= 0 else "CHOCH"
            import core.structure as ST
            atr = ST.atr_of(daily, i - 1) or (last_l["price"] * 0.02)
            mag = (last_l["price"] - c) / atr if atr else 0
            return {"type": typ, "direction": "SHORT", "level": last_l["price"],
                    "break_idx": i, "trend_before": tr,
                    "strength": round(min(100.0, 50 + mag * 25), 1)}
    return None


def find_shifts(daily, i0, i1):
    """扫描 [i0, i1] 全部结构转移(事件流生成器)。"""
    out = []
    last_break_idx = -99
    for i in range(max(25, i0), min(i1 + 1, len(daily))):
        s = structure_shift(daily, i)
        if s and i - last_break_idx >= 2:  # 去抖: 相邻bar连破只记首破
            out.append(s)
            last_break_idx = i
    return out