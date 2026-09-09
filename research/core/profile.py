# -*- coding: utf-8 -*-
"""core/profile.py —— V2 ITERATION 5: Stock Profile
蓝图 §29: 每股滚动 Profile: ATR%/换手/跳空频率/涨跌停频率/趋势持续性/均值回归/噪声/
平均摆幅/扫损深度/位移分布/FVG反应/OB反应/典型持有。
蓝图 §30: Stock Profile Cluster —— 行为聚类共享参数族, 不是一股一参数。

语义(决策时点 i, 无前视): 全部特征只用 [i-window, i] 数据。
输出: profile dict(14特征) + cluster 标签(KMeans-free 的分位数桶, 避免引入sklearn依赖)。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def stock_profile(daily, i, window=120):
    """计算 daily[i] 决策时点的滚动 Profile。i>=window 才有效。"""
    if i < window:
        return None
    w = daily[i - window:i + 1]
    closes = [b["c"] for b in w]
    highs = [b["h"] for b in w]
    lows = [b["l"] for b in w]
    vols = [b["v"] for b in w]
    n = len(w)
    if n < 30 or any(c <= 0 for c in closes):
        return None
    # ATR%
    trs = []
    for k in range(1, n):
        trs.append(max(highs[k] - lows[k], abs(highs[k] - closes[k - 1]), abs(lows[k] - closes[k - 1])))
    atr_pct = (sum(trs) / len(trs)) / closes[-1] * 100
    # 跳空频率: |open/prev_close-1|>1%
    gaps = sum(1 for k in range(1, n) if w[k]["o"] and abs(w[k]["o"] / closes[k - 1] - 1) > 0.01)
    gap_freq = gaps / n
    # 涨跌停频率(A股±10%/±20%近似): 单bar |ret|>9.5%
    limits = sum(1 for k in range(1, n) if closes[k - 1] and abs(closes[k] / closes[k - 1] - 1) > 0.095)
    limit_freq = limits / n
    # 趋势持续性: 自相关 lag1 of returns 符号一致率
    rets = [closes[k] / closes[k - 1] - 1 for k in range(1, n) if closes[k - 1] > 0]
    if len(rets) < 10:
        return None
    same_sign = sum(1 for k in range(1, len(rets)) if rets[k] * rets[k - 1] > 0)
    trend_persist = same_sign / (len(rets) - 1)
    # 均值回归: |ret_lag1 与 ret_lag0 负相关度(简化: 反转率)
    mean_reversion = 1.0 - trend_persist
    # 噪声: 日内振幅中位数(ADR)
    adrs = [(highs[k] - lows[k]) / closes[k] * 100 for k in range(n) if closes[k] > 0]
    adrs.sort()
    noise = adrs[len(adrs) // 2]
    # 平均摆幅: 20日摆动高低差
    seg = 20
    swings = []
    for s in range(0, n - seg, seg):
        seg_h = max(highs[s:s + seg]); seg_l = min(lows[s:s + seg])
        mid = (seg_h + seg_l) / 2
        if mid > 0:
            swings.append((seg_h - seg_l) / mid * 100)
    avg_swing = sum(swings) / len(swings) if swings else noise * 10
    # 换手代理: 平均量 / 中位量(量能稳定性)
    sv = sorted(vols)
    vol_stability = (sum(vols) / n) / sv[n // 2] if sv[n // 2] else 1.0
    return {"atr_pct": round(atr_pct, 3), "gap_freq": round(gap_freq, 4),
            "limit_freq": round(limit_freq, 5), "trend_persist": round(trend_persist, 3),
            "mean_reversion": round(mean_reversion, 3), "noise_adr_med": round(noise, 2),
            "avg_swing_20d": round(avg_swing, 2), "vol_stability": round(vol_stability, 3),
            "window": window, "bars": n}


def profile_cluster(profile, buckets=None):
    """把 profile 映射到行为聚类标签(分位数桶, 免 sklearn; 桶边界来自蓝图§25研究起点, 非拟合参数)。
    输出 'profile<vol>-<trend>' 形式: vol=low/mid/high, trend=mr/persist。"""
    if not profile:
        return None
    a = profile["atr_pct"]
    vol = "low" if a < 2.0 else ("mid" if a < 4.0 else "high")
    tp = profile["trend_persist"]
    trend = "persist" if tp >= 0.5 else "mr"
    return f"profile_{vol}_{trend}"


def profile_family_params(cluster):
    """聚类 → 共享参数族(蓝图 §30: Cluster→Shared parameter family)。
    研究起点值, 最终由 Walk-Forward 确定(蓝图 §63)。"""
    if not cluster:
        return {}
    base = {"sweep_floor": 0.4, "disp_min": 50, "sl_buf_atr": 0.5, "max_hold": 15,
            "retest_bars": 10}
    if "low" in cluster:
        return dict(base, sl_buf_atr=0.75, max_hold=20, disp_min=45)
    if "high" in cluster:
        return dict(base, sl_buf_atr=0.4, max_hold=10, disp_min=55, retest_bars=7)
    return base