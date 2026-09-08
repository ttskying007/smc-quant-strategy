# -*- coding: utf-8 -*-
"""core/fvg_ob.py —— V2 Structure Engine 2.0: FVG/OB/Reclaim 统一语义
蓝图 §7 剩余项 + §35 链条核心:
  FVG(公平价值缺口): 三根K模式 —— bullish: low[i+2] > high[i] (gap未回补)
  OB(订单块): 最后一根反向K(下跌段最后一根阴线/上涨段最后一根阳线), 其区间为需求/供给区
  Reclaim(收回): 价格跌破后 N 根内收盘收复关键位

语义规则(决策时点 i, 无前视):
  - FVG 检测于 i 处时只要求 i+1, i+2 已存在(gap 由 i-2,i-1,i 组成时在 i 可判定)
    本模块 fvg_at(daily, i): gap=bar[i-2..i] 三根, 在 i 收盘后判定 —— 用 daily[:i+1]
  - OB: 寻找最近与当前位移方向相反的连续K段末根
  - 全部带 quality(缺口大小/ATR, OB 段长度)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def atr_of_local(daily, i, n=14):
    if i < n + 1:
        return None
    trs = []
    for k in range(i - n + 1, i + 1):
        tr = max(daily[k]["h"] - daily[k]["l"],
                 abs(daily[k]["h"] - daily[k - 1]["c"]),
                 abs(daily[k]["l"] - daily[k - 1]["c"]))
        trs.append(tr)
    return sum(trs) / n


def fvg_at(daily, i, min_gap_atr=0.25):
    """判定 daily[i] 是否形成 FVG(三根模式 i-2, i-1, i; 在 i 收盘后判定, 无前视)。
    返回 None 或 {direction, low, high, mid, size_atr, filled}。"""
    if i < 2:
        return None
    a, b, c = daily[i - 2], daily[i - 1], daily[i]
    atr = atr_of_local(daily, i) or (c["c"] * 0.02)
    # bullish FVG: c.low > a.high (中间根急涨留下的上方缺口)
    if c["l"] > a["h"]:
        size = c["l"] - a["h"]
        size_atr = size / atr if atr else 0
        if size_atr >= min_gap_atr:
            return {"direction": "BULL", "low": a["h"], "high": c["l"],
                    "mid": round((a["h"] + c["l"]) / 2, 4),
                    "size_atr": round(size_atr, 3), "filled": False,
                    "idx": i}
    # bearish FVG: c.high < a.low
    if c["h"] < a["l"]:
        size = a["l"] - c["h"]
        size_atr = size / atr if atr else 0
        if size_atr >= min_gap_atr:
            return {"direction": "BEAR", "low": c["h"], "high": a["l"],
                    "mid": round((a["h"] if False else (c["h"] + a["l"]) / 2), 4),
                    "size_atr": round(size_atr, 3), "filled": False,
                    "idx": i}
    return None


def is_fvg_filled(daily, i, fvg, bars=10):
    """FVG 是否在其后 bars 根内被回补(价格回到缺口内触及 mid)。i 为当前决策点。"""
    for k in range(fvg["idx"] + 1, min(i + 1, fvg["idx"] + 1 + bars)):
        b = daily[k]
        if b["l"] <= fvg["mid"] if fvg["direction"] == "BULL" else b["h"] >= fvg["mid"]:
            return True
    return False


def order_block(daily, i, direction="BULL", lookback=12, max_ob_bars=3):
    """寻找 i 之前的最近 OB。
    BULL: 先回溯跳过上涨腿(连续阳线), 其根部的连续阴线段(最多 max_ob_bars 根, 靠近脉冲的)
    即为需求 OB —— 上涨脉冲的起点。
    返回 None 或 {direction, low, high, mid, bars_len, freshness}。"""
    if i < 3:
        return None
    floor = max(0, i - lookback)
    k = i - 1
    if direction == "BULL":
        while k > floor and daily[k]["c"] >= daily[k]["o"]:
            k -= 1  # 跳过上涨腿
        seg = []
        while k >= floor and daily[k]["c"] < daily[k]["o"] and len(seg) < max_ob_bars:
            seg.append(k)
            k -= 1
    else:
        while k > floor and daily[k]["c"] <= daily[k]["o"]:
            k -= 1
        seg = []
        while k >= floor and daily[k]["c"] > daily[k]["o"] and len(seg) < max_ob_bars:
            seg.append(k)
            k -= 1
    if not seg:
        return None
    lo = min(daily[j]["l"] for j in seg)
    hi = max(daily[j]["h"] for j in seg)
    return {"direction": direction, "low": round(lo, 4), "high": round(hi, 4),
            "mid": round((lo + hi) / 2, 4), "bars_len": len(seg),
            "freshness": round(1.0 - min(1.0, (i - 1 - seg[0]) / max(1, lookback)), 3),
            "idx_last": seg[0]}


def reclaim_of(daily, i, level, direction="LONG", bars=5):
    """收回语义: 窗口 [i-bars+1, i] 内某根收盘重新收上 level(此前确有跌破)。
    判定于 i(无前视)。返回 (reclaimed, reclaim_idx)。
    '确有失去'的验证: 收回根之前 bars 根内存在收盘低于 level 的 bar。"""
    if i < bars + 2:
        return False, None
    for k in range(max(0, i - bars + 1), i + 1):
        beyond = daily[k]["c"] > level if direction == "LONG" else daily[k]["c"] < level
        if not beyond:
            continue
        # 验证此前确有失去
        for j in range(max(0, k - bars), k):
            lost = daily[j]["c"] < level if direction == "LONG" else daily[j]["c"] > level
            if lost:
                return True, k
        return False, None  # 收回了但从未失去(一直在上方)
    return False, None