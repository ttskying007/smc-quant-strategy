# -*- coding: utf-8 -*-
"""core/profile.py —— V2 ITERATION 5: Stock Profile
蓝图 §29: 每股滚动 Profile(目标 14+ 特征); 蓝图 §30: 行为聚类共享参数族, 不是一股一参数。

Profile V1(第三轮深审 A7 诚实标注): 当前 9 特征 —— ATR%/跳空频率/涨跌停频率(板块统一 A8)/
趋势持续性/均值回归/噪声ADR/20日平均摆幅/量能稳定性/窗口元数据。
待补(蓝图全量): 扫损深度/位移分布/FVG反应/OB反应/典型持有。

F8(2026-09-09 第四轮后续): 已补齐 5 特征 → Profile V2 = 14 特征(sweep_depth_med/disp_mean/
disp_q75/fvg_reaction/ob_reaction/typical_hold_pct)。

语义(决策时点 i, 无前视): 全部特征只用 [i-window, i] 数据。
输出: profile dict + cluster 标签(分位数桶, 免 sklearn)。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def stock_profile(daily, i, window=120, code=""):
    """计算 daily[i] 决策时点的滚动 Profile。i>=window 才有效。
    code: 6位股票代码(用于 A8 板块涨跌停规则; 空则按 10% 主板近似)。
    Profile V2(14 特征, F8 补齐): 基础9 + sweep_depth_med/disp_mean/disp_q75/
    fvg_reaction/ob_reaction/typical_hold_pct。全部只用 [i-window, i] 数据(无前视)。"""
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
    # 涨跌停频率(第三轮深审A8: 统一 core/limits 板块规则, 替代原 9.5% 近似)
    from core.limits import daily_limit_pct
    limits = 0
    for k in range(1, n):
        if closes[k - 1] > 0:
            _d8k = w[k].get("t") if isinstance(w[k].get("t"), str) and len(str(w[k].get("t"))) >= 8 else None
            lim = daily_limit_pct(code, _d8k) / 100.0
            if abs(closes[k] / closes[k - 1] - 1) >= lim - 1e-4:
                limits += 1
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
    # ---- F8(第三轮深审遗留): 补齐 14+ 特征的 5 项 ----
    # 扫损深度: 窗口内 bar 下破 20bar 前低后收回的深度中位数(ATR%)
    import core.liquidity as LQ
    sweep_depths = []
    for k in range(25, n):
        p20 = min(x["l"] for x in w[max(0, k - 20):k])
        b = w[k]
        if b["l"] < p20 and b["c"] > p20:
            sweep_depths.append((p20 - b["l"]) / (closes[k] or 1) * 100)
    sweep_depth_med = round(sorted(sweep_depths)[len(sweep_depths) // 2], 3) if sweep_depths else 0.0
    # 位移分布: 窗口 displacement_score 的均值与上四分位
    import core.displacement as DS
    dsc = [DS.displacement_score(w, k)["score"] for k in range(25, n)]
    dsc.sort()
    disp_mean = round(sum(dsc) / len(dsc), 1) if dsc else 0.0
    disp_q75 = round(dsc[int(len(dsc) * 0.75)], 1) if dsc else 0.0
    # FVG 反应: FVG 出现后 5bar 内回补(触碰 mid)比例
    import core.fvg_ob as FO
    fvg_n = fvg_fill = 0
    for k in range(25, n - 5):
        f_ = FO.fvg_at(w, k)
        if f_:
            fvg_n += 1
            for j in range(k + 1, min(n, k + 6)):
                if w[j]["l"] <= f_["mid"]:
                    fvg_fill += 1
                    break
    fvg_reaction = round(fvg_fill / fvg_n, 3) if fvg_n else None
    # OB 反应: OB 出现后 5bar 内回踩 mid 比例
    ob_n = ob_touch = 0
    for k in range(25, n - 5):
        o_ = FO.order_block(w, k, "BULL")
        if o_:
            ob_n += 1
            for j in range(k + 1, min(n, k + 6)):
                if w[j]["l"] <= o_["mid"]:
                    ob_touch += 1
                    break
    ob_reaction = round(ob_touch / ob_n, 3) if ob_n else None
    # 典型持有: 20bar 区间收益绝对值中位数(持有尺度的代理)
    holds = []
    for s in range(0, n - 20, 5):
        r = closes[s + 20] / closes[s] - 1
        holds.append(abs(r) * 100)
    typical_hold = round(sorted(holds)[len(holds) // 2], 2) if holds else None
    return {"atr_pct": round(atr_pct, 3), "gap_freq": round(gap_freq, 4),
            "limit_freq": round(limit_freq, 5), "trend_persist": round(trend_persist, 3),
            "mean_reversion": round(mean_reversion, 3), "noise_adr_med": round(noise, 2),
            "avg_swing_20d": round(avg_swing, 2), "vol_stability": round(vol_stability, 3),
            # F8 新增 5 特征(→14)
            "sweep_depth_med": sweep_depth_med, "disp_mean": disp_mean, "disp_q75": disp_q75,
            "fvg_reaction": fvg_reaction, "ob_reaction": ob_reaction,
            "typical_hold_pct": typical_hold,
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