# -*- coding: utf-8 -*-
"""core/risk.py —— V2 ITERATION 8: 结构化 TP/SL
蓝图 §45-47:
  SL = 结构失效优先(POI 下方/扫损池下沿), ATR 缓冲兜底
  TP1 = Internal Liquidity(近端 swing/前高)
  TP2 = External Liquidity(区间外沿/60D 极值方向)
  TP3 = HTF Liquidity(120D+ 极值), Runner

输出结构化 tp/sl dict + EV 估算。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.liquidity import liquidity_pools, nearest_pools


def structured_tp_sl(daily, i, zone, direction="LONG", atr_pct=0.02, fee_pct=0.2):
    """由 zone(来自 core/entry.entry_zone) + 流动性池构造结构化 TP/SL。
    SL: zone.invalid_price 再留 0.5×ATR% 缓冲(结构失效+执行缓冲)
    TP1: 距 fill 最近的上方 BSL 池(Internal); 无池 → 1×risk
    TP2: 更远 BSL(External, 60D 类优先); 无 → 2×risk
    TP3: 窗口内最高 BSL/最高价(HTF); 无 → 3×risk
    返回 {sl, tp1, tp2, tp3, rr1, rr2, rr3, ev1, structure_based}"""
    if zone is None or i >= len(daily):
        return None
    entry = zone["optimal_entry"]
    sl_raw = zone["invalid_price"]
    atr_abs = entry * atr_pct
    sl = sl_raw - 0.5 * atr_abs  # 结构失效 + 执行缓冲
    risk = entry - sl
    if risk <= 0:
        return None
    pools = liquidity_pools(daily, i)
    bsls = [p for p in pools if p["side"] == "BSL" and p["price"] > entry]
    bsls.sort(key=lambda p: p["price"])
    tps = []
    for lvl_mult in (1, 2, 3):
        if len(bsls) >= lvl_mult:
            cand = bsls[lvl_mult - 1]["price"]
            # 池目标至少 lvl_mult*0.6×risk, 防止极近池给出超低 RR
            if cand >= entry + lvl_mult * 0.6 * risk:
                tps.append(cand)
            else:
                tps.append(entry + lvl_mult * risk)
        else:
            tps.append(entry + lvl_mult * risk)
    tp1, tp2, tp3 = tps
    # EV 估算(第三轮深审 A6 降级声明): p_win=0.5 与固定 TP 权重是【研究示例值】,
    # 非条件期望值。生产准入只允许用 rr1/rr2/rr3(结构RR); ev_est 严禁用于买卖决策,
    # 直至 Walk-Forward 历史条件概率 P(TP1/TP2/TP3/SL) 建成为止。
    f = fee_pct / 100
    p_win = 0.5  # RESEARCH-ONLY placeholder
    ev = (0.5 * (0.5 * (tp1 / entry - 1) + 0.3 * (tp2 / entry - 1) + 0.2 * (tp3 / entry - 1))
          - 0.5 * (risk / entry)) - f
    return {"sl": round(sl, 4), "tp1": round(tp1, 4), "tp2": round(tp2, 4), "tp3": round(tp3, 4),
            "rr1": round((tp1 - entry) / risk, 2), "rr2": round((tp2 - entry) / risk, 2),
            "rr3": round((tp3 - entry) / risk, 2),
            "ev_est": round(ev * 100, 3),
            "ev_est_research_only": True,  # A6: 显式标记, 消费方必须检查
            "structure_based": len(bsls) >= 2}