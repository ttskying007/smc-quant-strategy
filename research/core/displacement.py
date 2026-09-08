# -*- coding: utf-8 -*-
"""core/displacement.py —— V1 蓝图 §12 Displacement 语义化打分
消融证据（2026-09-08, SMC逐门消融）：位移签名是 W1D1D4 全链路唯一有信息量的过滤器。
蓝图要求：不能简单用"涨幅大"定义，应综合 Body/ATR、Close Location、Volume、Gap、
Consecutive Bars、Structure Break、FVG Formation 形成连续 DisplacementScore(0~100)。

打分组件（全部只用 ≤ 当前bar 数据，无前视）：
  1. body_atr    : 实体/ATR 比值（大资金推动的核心签名）         0-30
  2. close_loc   : 收盘位于当日区间上 35% + 创 BOS 窗口收盘新高   0-20
  3. volume      : 60日真 z-score ≥1/≥2/≥3 递进                  0-20
  4. gap         : 跳空缺口方向一致（bar.o > prev.c）             0-10
  5. consecutive : 连续同向 bar ≥2/≥3                            0-10
  6. struct_brk  : 本 bar 收盘突破近 N 根确认 swing high（BOS性） 0-10
总分 0~100；分桶: <30 弱 / 30-60 正常 / 60-80 强 / ≥80 极强
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.structure import atr_of, is_swing_high


def displacement_score(daily, i, swing_lows=None, lookback_swing=60):
    """计算 daily[i] 的位移分。daily: [{t,o,h,l,c,v}] 按时间升序。
    返回 {"score": int, "bucket": str, "parts": {...}}。
    swing_lows 可选预计算确认 swing high 索引列表以省时。"""
    b = daily[i]
    atr = atr_of(daily, i - 1) or 0
    parts = {}

    # 1) body/ATR（0-30）: 实体 = |c-o|；≥1ATR 满分，按比例给分
    body = abs(b["c"] - b["o"])
    parts["body_atr"] = round(min(30.0, (body / atr * 30.0) if atr > 0 else 0.0), 1)

    # 2) close location（0-20）: 上35%给12分；收盘破前10根高点(不含本根)再加8分
    rng = b["h"] - b["l"]
    loc = (b["c"] - b["l"]) / rng if rng > 0 else 0.0
    _p2 = 12.0 if (rng > 0 and loc >= 0.65) else loc * 12.0 / 0.65
    if i >= 1:
        hi10 = max(daily[k]["h"] for k in range(max(0, i - 10), i))
        if b["c"] > hi10:
            _p2 += 8.0
    parts["close_loc"] = round(min(20.0, _p2), 1)

    # 3) volume z-score（0-20）: 60日真 z（窗口含当前bar，与 wdh vol_z 口径一致）
    n = min(60, i + 1)
    if n >= 20:
        vs = [daily[k]["v"] for k in range(i + 1 - n, i + 1)]
        mu = sum(vs) / n
        var = sum((x - mu) ** 2 for x in vs) / n
        sd = var ** 0.5
        z = (b["v"] - mu) / sd if sd > 0 else 0.0
        parts["volume"] = round(min(20.0, max(0.0, (z - 0.5) / 2.5 * 20.0)), 1)
    else:
        parts["volume"] = 0.0

    # 4) gap（0-10）: 阳线向上跳空
    prev_c = daily[i - 1]["c"] if i >= 1 else b["o"]
    _g = (b["o"] / prev_c - 1) if prev_c > 0 else 0.0
    gap_dir = 1 if b["c"] > b["o"] else -1
    parts["gap"] = round(min(10.0, max(0.0, _g / 0.03 * 10.0)) if gap_dir > 0 and _g > 0 else 0.0, 1)

    # 5) consecutive（0-10）: 连续阳线（含本根）
    cons = 0
    for k in range(i, max(-1, i - 4), -1):
        if daily[k]["c"] > daily[k]["o"]:
            cons += 1
        else:
            break
    parts["consecutive"] = {1: 3.0, 2: 6.0, 3: 8.0}.get(cons, 10.0 if cons >= 4 else 0.0)

    # 6) structure break（0-10）: 收盘突破近 lookback 根内最新确认 swing high
    brk = 0.0
    if swing_lows is None:
        sw = [j for j in range(max(0, i - lookback_swing), i - 2) if is_swing_high(daily, j)]
    else:
        sw = [j for j in swing_lows if i - lookback_swing <= j <= i - 3]
    if sw:
        last_sw = daily[sw[-1]]["h"]
        if b["c"] > last_sw:
            brk = 10.0
    parts["struct_brk"] = brk

    score = round(sum(parts.values()))
    bucket = ("<30 弱" if score < 30 else "30-60 正常" if score < 60
              else "60-80 强" if score < 80 else "≥80 极强")
    return {"score": score, "bucket": bucket, "parts": parts}
