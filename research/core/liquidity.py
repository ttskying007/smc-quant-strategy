# -*- coding: utf-8 -*-
"""core/liquidity.py —— V2 Structure Engine 2.0 第一批: Liquidity 统一语义
蓝图 §9: 流动性不应只是 previous high/low, 需形成:
  - External Liquidity: PDH/PDL(前日高/低), PWH/PWL(前周高/低), 60D/120D 高低, 确认Swing高低, 等高低(EQ)
  - Internal Liquidity: 短期Swing, FVG边缘(预留), 内部OB(预留)
  - 池质量: age/touch_count/distance/swing_strength/equalness → LiquidityScore 0~100

语义规则(无前视, 全部决策时点可得):
  - 池只由 i 之前的 bar 构成(swing 需确认窗口 PIVOT_R)
  - touch = bar.low 触及池位(±tol)后收回 → touch_count++
  - equalness: 相邻两池距离 < tol×2 → EQ池(更强磁吸)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.structure import is_swing_high, is_swing_low, atr_of

PIVOT_R = 3  # 与 structure/structure.py 确认窗口一致


def liquidity_pools(daily, i, lookback=120):
    """计算 daily[i] 决策时点可见的流动性池列表(全方向)。
    返回 [{kind, side, price, idx, age, touch_count, equal, score}]。
    side: 'SSL'(卖方流动性=下方买盘承接) | 'BSL'(买方流动性=上方卖盘阻力)。"""
    if i < 25:
        return []
    atr = atr_of(daily, i - 1) or 0
    tol = max(0.003, (atr / (daily[i - 1]["c"] or 1)) * 0.5) if atr > 0 else 0.003
    pools = []
    seen_px = []

    def add_pool(kind, side, price, idx):
        if price is None or price <= 0 or idx > i - 1:
            return
        # 等高低合并: 已有池距离 < 2tol → 合并为 EQ
        for p in pools:
            if p["side"] == side and abs(p["price"] - price) / price < 2 * tol:
                p["equal"] = True
                p["price"] = round((p["price"] + price) / 2, 4)
                return
        # touch 计数: i 之前触及池位的 bar 数
        tc = 0
        for k in range(idx + 1, i):
            lo, hi = daily[k]["l"], daily[k]["h"]
            if side == "BSL" and hi >= price * (1 - tol) and daily[k]["c"] < price:
                tc += 1
            elif side == "SSL" and lo <= price * (1 + tol) and daily[k]["c"] > price:
                tc += 1
        age = i - idx
        pools.append({"kind": kind, "side": side, "price": round(price, 4),
                      "idx": idx, "age": age, "touch_count": tc,
                      "equal": False,
                      "_score_raw": (age, tc)})

    lb0 = max(0, i - lookback)
    # 确认 swing(无前视: j+PIVOT_R < i)
    swing_highs = [j for j in range(lb0 + PIVOT_R, i - PIVOT_R) if is_swing_high(daily, j)]
    swing_lows = [j for j in range(lb0 + PIVOT_R, i - PIVOT_R) if is_swing_low(daily, j)]
    for j in swing_highs:
        add_pool("SWING", "BSL", daily[j]["h"], j)
    for j in swing_lows:
        add_pool("SWING", "SSL", daily[j]["l"], j)
    # 外部参考: 前日高低(PDH/PDL)
    # FIX(2026-09-13, 第八轮审计 5.4): 原 add_pool 门槛 `idx >= i-1` 拒绝恰好以
    # idx=i-1 传入的 PDH/PDL —— 池永远为空(审计 8.4 复现), 文档定义的 External
    # Liquidity 从未进入 SMC 流动性池/评分/sweep 链。改为 idx > i-1(仅排除当日)。
    if i >= 1:
        add_pool("PDH", "BSL", daily[i - 1]["h"], i - 1)
        add_pool("PDL", "SSL", daily[i - 1]["l"], i - 1)
    # 60/120日高/低(只取窗口内、i之前)
    # FIX(2026-09-09, 第三轮深审A1): 60D SSL 索引错误——原代码价格取窗口最低low但索引
    # 用 max(key=low) 指向最高low的bar, price/idx/age/touch_count 不同源, 污染下游
    # 评分/SL/TP。改为 min(key=low) 使索引与价格同根K线。
    w60 = daily[max(0, i - 60):i]
    if w60:
        b0_60 = max(0, i - 60)
        _hi_i = max(range(len(w60)), key=lambda k: w60[k]["h"]) + b0_60
        _lo_i = min(range(len(w60)), key=lambda k: w60[k]["l"]) + b0_60
        add_pool("60D", "BSL", daily[_hi_i]["h"], _hi_i)
        add_pool("60D", "SSL", daily[_lo_i]["l"], _lo_i)
    # 评分
    for p in pools:
        age, tc = p["_score_raw"]
        # age: 太新(<3)弱, 太老(>120)弱, 20~90 最强 → 钟形
        age_s = 30.0 if 20 <= age <= 90 else (15.0 if 3 <= age < 20 else 5.0)
        # touch: 1次20, 2次15(已消耗部分), >=3 5(大概率已破)
        tc_s = {0: 25.0, 1: 20.0, 2: 12.0}.get(tc, 5.0)
        # equal 加成: 等高低是更强磁吸
        eq_s = 25.0 if p["equal"] else 0.0
        # kind: SWING 20 / PDH/PDL 15 / 60D 20
        k_s = {"SWING": 20.0, "PDH": 15.0, "60D": 20.0}.get(p["kind"], 10.0)
        p["score"] = round(min(100.0, age_s + tc_s + eq_s + k_s), 1)
        del p["_score_raw"]
    pools.sort(key=lambda p: -p["score"])
    return pools


def nearest_pools(pools, price, side=None, n=3):
    """距当前价最近的 n 个池(按距离升序)。"""
    cand = [p for p in pools if (side is None or p["side"] == side)]
    cand.sort(key=lambda p: abs(p["price"] / price - 1) if price else 9e9)
    return cand[:n]