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
    # EV 估算: WR 假设按 bucket(保守 0.45/0.35/0.25 到各 TP), 分批 TP1 50% TP2 30% TP3 20%
    # net = 费后
    f = fee_pct / 100
    ev = (0.45 * ((tp1 / entry - 1) - f) + 0.35 * ((tp2 / entry - 1) - f)
          + 0.25 * ((tp3 / entry - 1) - f) - 0.45 * 0 + (-0.0) )
    # 简化 EV: 期望收益 = Σ p_i×(tp_i收益) − (1−WR_total)×SL损失; WR_total 保守 0.5
    p_win = 0.5
    ev = (0.5 * (0.5 * (tp1 / entry - 1) + 0.3 * (tp2 / entry - 1) + 0.2 * (tp3 / entry - 1))
          - 0.5 * (risk / entry)) - f
    return {"sl": round(sl, 4), "tp1": round(tp1, 4), "tp2": round(tp2, 4), "tp3": round(tp3, 4),
            "rr1": round((tp1 - entry) / risk, 2), "rr2": round((tp2 - entry) / risk, 2),
            "rr3": round((tp3 - entry) / risk, 2),
            "ev_est": round(ev * 100, 3), "structure_based": len(bsls) >= 2}