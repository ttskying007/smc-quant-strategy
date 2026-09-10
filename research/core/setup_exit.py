# -*- coding: utf-8 -*-
"""core/setup_exit.py —— V3 P0-1: Setup Engine 单一退出实现(Single Source of Truth)
V3审计§六/问题2: setup_engine_paper.py 注释写"TP3结构位"但结算无 TP 逻辑 —— 回测一个退出/
PAPER 一个退出是 SHADOW→PAPER→REAL 晋级的语义分叉, 必须合并为一份实现。

本模块 = Setup Engine 候选(POI 结构)的唯一退出语义, 供:
  - run_sequence_v2 回测实验(B1 SHADOW 口径)
  - setup_engine_paper.py PAPER 台账
  - 未来统一 SetupEngine 生产链
全部调用 settle_setup()。退出规则(与 B3 宽 SL 口径一致):
  SL  = invalid_price − 1.5×ATR(结构失效位 + 缓冲)
  TIME = fill 后第 max_bars 根收盘(默认15)
  TP   = 3R 结构位(rr = (target−entry)/risk ≥ tp_rr 时触发, 默认 3R)
版本: setup_exit_v1; 任何修改必须同步三处消费方并 bump EXIT_VERSION。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXIT_VERSION = "setup_exit_v1"


def settle_setup(daily, i, setup, fee_pct=0.2, max_bars=15, tp_rr=3.0):
    """统一退出模拟。i = 决策点(信号bar); setup 来自 run_sequence_v2().setup()。
    返回 dict(status, ret_pct, fill_price, fill_idx, sl, exit_reason) 或 None(无撮合)。
    撮合: fill_in_zone STRICT_LIMIT(A4 生产默认)。"""
    from core.entry import fill_in_zone
    poi = setup["poi"]
    zone = {"zone_low": poi["low"], "zone_high": poi["high"],
            "invalid_price": poi["low"] * 0.97, "optimal_entry": poi["mid"]}
    fill = fill_in_zone(daily, i, zone, max_bars=5, fill_mode="STRICT_LIMIT")
    if fill is None or fill.get("fill_price") is None:
        if fill and fill.get("mode") == "INVALIDATED_BEFORE_FILL":
            return {"status": "INVALIDATED", "ret_pct": None, "exit_reason": "INVALIDATED_BEFORE_FILL",
                    "exit_version": EXIT_VERSION}
        return None
    fi, fpx = fill["fill_idx"], fill["fill_price"]
    return _settle_from_fill(daily, fi, fpx, zone["invalid_price"], fee_pct, max_bars, tp_rr)


def settle_from_record(daily, i_fill, fill_price, invalid_price, fee_pct=0.2,
                       max_bars=15, tp_rr=3.0):
    """PAPER 台账推进用: 已知成交(i_fill, fill_price)后续一退出。
    与 settle_setup 后半段同代码路径(单源)。"""
    return _settle_from_fill(daily, i_fill, fill_price, invalid_price, fee_pct, max_bars, tp_rr)


def _settle_from_fill(daily, fi, fpx, invalid_price, fee_pct, max_bars, tp_rr):
    n = len(daily)
    try:
        from core.structure import atr_of
        atr = atr_of(daily, fi - 1) or 0.02 * fpx
    except Exception:
        atr = 0.02 * fpx
    sl = invalid_price - 1.5 * atr
    risk = fpx - sl
    tp = fpx + tp_rr * risk if risk > 0 else None
    last_k = min(n - 1, fi + max_bars)
    for k in range(fi + 1, last_k + 1):
        b = daily[k]
        if b["l"] <= sl:
            return {"status": "SL", "ret_pct": round((sl / fpx - 1) * 100 - fee_pct, 3),
                    "exit_reason": "SL_HIT", "sl": round(sl, 4), "tp": round(tp, 4) if tp else None,
                    "fill_price": fpx, "fill_idx": fi, "exit_idx": k, "exit_version": EXIT_VERSION}
        if tp and b["h"] >= tp:
            return {"status": "TP", "ret_pct": round((tp / fpx - 1) * 100 - fee_pct, 3),
                    "exit_reason": "TP_STRUCT", "sl": round(sl, 4), "tp": round(tp, 4),
                    "fill_price": fpx, "fill_idx": fi, "exit_idx": k, "exit_version": EXIT_VERSION}
        if k == last_k:
            return {"status": "TIME", "ret_pct": round((b["c"] / fpx - 1) * 100 - fee_pct, 3),
                    "exit_reason": "TIME_STOP", "sl": round(sl, 4), "tp": round(tp, 4) if tp else None,
                    "fill_price": fpx, "fill_idx": fi, "exit_idx": k, "exit_version": EXIT_VERSION}
    return {"status": "OPEN", "ret_pct": None, "exit_reason": "NOT_YET",
            "sl": round(sl, 4), "tp": round(tp, 4) if tp else None,
            "fill_price": fpx, "fill_idx": fi, "exit_version": EXIT_VERSION}