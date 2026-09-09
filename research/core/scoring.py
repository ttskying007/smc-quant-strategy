# -*- coding: utf-8 -*-
"""core/scoring.py —— V2 ITERATION 10: TradeScore
蓝图 §62-63: Hard Gates + Soft Scores 替代过度 AND。
组件(全部决策时点可得, 无前视):
  StructureScore  : 结构转移强度(CHOCH/BOS strength) + 池质量(liquidity score)
  SequenceScore   : 链条 Δt 紧凑性(事件间隔越紧凑越强) + 链完整度
  DisplacementScore: core.displacement 评分(直接复用)
  LocationScore   : 入场位置质量(距 invalid 近好, 复用 entry_score 组件)
组合: TradeScore = 0.35×Structure + 0.20×Sequence + 0.30×Displacement + 0.15×Location
权重为研究起点(蓝图 §63: 初始权重只能作研究起点, 最终由 Walk-Forward 确定)。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def structure_score(shift, pools):
    """结构分: 转移强度(0-100)×0.6 + 最优池分(0-100)×0.4。"""
    if not shift:
        return 0.0
    s = float(shift.get("strength") or 50)
    pool_s = 0.0
    if pools:
        pool_s = max(p["score"] for p in pools)
    return round(min(100.0, s * 0.6 + pool_s * 0.4), 1)


def sequence_score(dt_days_list):
    """时序分: Δt 越紧凑越高。全 Δt<=3 → 100; 平均 Δt 线性衰减到 0(@30d)。空链 0。"""
    if not dt_days_list:
        return 0.0
    avg_dt = sum(dt_days_list) / len(dt_days_list)
    return round(max(0.0, min(100.0, 100.0 * (1 - avg_dt / 30.0))), 1)


def displacement_score(sc_dict):
    """位移分: 直接复用 core.displacement 的 0-100。"""
    if not sc_dict:
        return 0.0
    return float(sc_dict.get("score") or 0)


def location_score(zone):
    """位置分: 复用 entry_zone 的 entry_score(已含距离/POI质量/RR/宽度)。"""
    if not zone:
        return 0.0
    return float(zone.get("entry_score") or 0)


WEIGHTS = {"structure": 0.35, "sequence": 0.20, "displacement": 0.30, "location": 0.15}


def trade_score(shift, pools, dt_days_list, disp_dict, zone):
    """组合 TradeScore 0-100 + 分量明细。"""
    parts = {
        "structure": structure_score(shift, pools),
        "sequence": sequence_score(dt_days_list),
        "displacement": displacement_score(disp_dict),
        "location": location_score(zone),
    }
    total = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)
    return {"score": round(min(100.0, total), 1), "parts": parts,
            "bucket": ("A_80_100" if total >= 80 else
                       "B_60_80" if total >= 60 else
                       "C_40_60" if total >= 40 else "D_0_40")}


# Hard Gates(蓝图 §62: 只留真正不可协商的)
def hard_gates_passed(zone, rr_min=0.8):
    """硬门: ①zone 合法几何 ②最低 RR。其余全部下放为 score。"""
    if zone is None:
        return False, "NO_ZONE"
    if zone.get("risk_at_optimal", 0) <= 0:
        return False, "BAD_GEOMETRY"
    rr = (zone.get("tp1", 0) - zone["optimal_entry"]) / zone["risk_at_optimal"]
    if rr < rr_min:
        return False, "RR_TOO_LOW"
    return True, "OK"