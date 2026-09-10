# -*- coding: utf-8 -*-
"""core/entry.py —— V2 ITERATION 7: Entry Zone 引擎
蓝图 §40-44: Signal 与 Entry Opportunity 拆开。
每个 READY setup 输出:
  zone_low / zone_high / optimal_entry / aggressive_entry / conservative_entry
  invalid_price(结构失效位) / rr_at_optimal / entry_score 0-100

语义(决策时点 i, 无前视):
  POI 区间(来自 fvg_ob: FVG 或 OB) = 入场区骨架
  invalid_price = POI.low × (1 - buf) 或扫损池位下方(结构失效)
  optimal = POI mid(回测中点入场)
  aggressive = zone 上沿(先到先成交, fill率高)
  conservative = zone 下沿(更优价, fill率低)
  entry_score = 位置质量(距 invalid 近好) + POI 质量(FVG size/OB bars) + RR
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def entry_zone(poi, price, invalid_price, atr_pct=0.02, fee_pct=0.2):
    """由 POI(FVG/OB dict) + 失效位构造入场区。
    poi: {low, high, mid, ...}; price: 当前价; invalid_price: 结构失效价(LONG: 下方)。
    返回 zone dict 或 None。"""
    if not poi or price is None or price <= 0 or invalid_price is None:
        return None
    zl, zh = poi["low"], poi["high"]
    if zl >= zh or zl <= 0:
        return None
    # 防御: 失效位必须在 zone 下方(LONG), 否则几何非法
    if invalid_price >= zl:
        invalid_price = zl * (1 - 0.5 * atr_pct)
    opt = poi.get("mid") or (zl + zh) / 2
    risk = opt - invalid_price
    if risk <= 0:
        return None
    # RR @ 最小目标(1×risk 上方保守, 真正 TP 由 risk.py 结构目标定)
    rr1 = 1.0
    tp1 = opt + rr1 * risk
    # 位置质量: 现价离 zone 中点越近越好; 已远离(zone 上方 >1 ATR) = late → 降分
    dist_atr = (price - opt) / (price * atr_pct) if price * atr_pct > 0 else 0
    loc_s = max(0.0, 30.0 - 15.0 * abs(dist_atr))
    # POI 质量: FVG size_atr / OB bars_len → 归一 0-25
    if "size_atr" in poi:
        poi_s = min(25.0, poi["size_atr"] * 25.0)
    else:
        poi_s = min(25.0, poi.get("bars_len", 1) * 8.0)
    # RR 加成(以 tp1 保守): 固定 rr1 时按 risk 占价比例的倒数(风险越小越好)
    risk_pct_of_price = risk / opt
    rr_s = max(0.0, min(25.0, 25.0 * (0.05 / max(0.01, risk_pct_of_price)) / 5.0))
    # zone 宽度: 过宽的 zone(>4 ATR%)说明 POI 粗糙 → 减分; 1-2% 最好
    width_pct = (zh - zl) / opt
    wid_s = 20.0 if 0.005 <= width_pct <= 0.02 else (12.0 if width_pct < 0.005 else max(0.0, 20.0 - (width_pct - 0.02) * 400))
    score = min(100.0, loc_s + poi_s + rr_s + wid_s)
    return {"zone_low": round(zl, 4), "zone_high": round(zh, 4),
            "optimal_entry": round(opt, 4),
            "aggressive_entry": round(zh, 4),
            "conservative_entry": round(zl, 4),
            "invalid_price": round(invalid_price, 4),
            "risk_at_optimal": round(risk, 4),
            "tp1": round(tp1, 4), "rr1": rr1,
            "entry_score": round(score, 1),
            "late_flag": dist_atr > 1.5}


def fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT"):
    """入场撮合语义(第三轮深审 A4 三模式):
      STRICT_LIMIT(生产默认): 必须真实触价 —— bar.low <= zone_high 才成交, 成交价=limit 触价
        (zone_high 挂单价); 无 open fallback; 开盘即在 zone 下方(未破invalid)按开盘成交(可观测更优)。
      TOUCH_LIMIT(宽松研究): 同 STRICT 但跳空穿越 zone 下方也按 zone_high 记(高估成交质量)。
      MARKET_OPEN(最宽): i+1 开盘直接市价成交(无论位置)。
    若 max_bars 内先破 invalid → INVALIDATED_BEFORE_FILL(模式无关)。"""
    if zone is None or i + 1 >= len(daily):
        return None
    if fill_mode == "MARKET_OPEN":
        k = i + 1
        if k >= len(daily):
            return None
        b = daily[k]
        if b["l"] <= zone["invalid_price"]:
            return {"fill_idx": k, "fill_price": None, "mode": "INVALIDATED_BEFORE_FILL"}
        return {"fill_idx": k, "fill_price": round(b["o"], 4), "mode": "MARKET_OPEN"}
    for k in range(i + 1, min(len(daily), i + 1 + max_bars)):
        b = daily[k]
        if b["l"] <= zone["invalid_price"]:
            return {"fill_idx": k, "fill_price": None, "mode": "INVALIDATED_BEFORE_FILL"}
        if b["l"] <= zone["zone_high"]:
            px = zone["zone_high"]  # 挂单价(触价成交)
            # 开盘即低于 zone(未破invalid): 开盘可观测更优价, 按开盘成交
            if b["o"] < zone["zone_low"]:
                px = b["o"]
            elif b["o"] < zone["zone_high"]:
                px = b["o"]  # 开盘已在 zone 内: 开盘价可成交
            return {"fill_idx": k, "fill_price": round(px, 4),
                    "mode": "STRICT_LIMIT" if fill_mode == "STRICT_LIMIT" else "TOUCH_LIMIT"}
    return None