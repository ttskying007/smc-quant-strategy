# -*- coding: utf-8 -*-
"""统一执行模块（审计 F07）—— 回测与纸面共用同一套执行语义。

核心原则：
1. 单一 Execution 核心：入场约束、逐 bar 触发（TP/SL/时间）、滑点、涨跌停/停牌
   由本模块实现，wdh_engine.replay 与 paper_sim.realtime_monitor 都调用它
2. 参数从 config.py 读取（FEE / SLIPPAGE），不再各自硬编码
3. 输出统一结构 {reason, exit_price, hold, mfe_r, mae_r, skipped}
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as CFG

FEE = CFG.FEE_PCT
SLIPPAGE = CFG.SLIPPAGE
MAX_HOLD_DEFAULT = CFG.MAX_HOLD if hasattr(CFG, "MAX_HOLD") else 12


def entry_ok(daily, entry_idx, ep, sl, prev_close=None):
    """A 股入场约束（F08）：
    ① 一字涨停开盘买不到 → 返回 (False, 'SKIP_LIMIT_UP')
    ② 入场价无效 → (False, 'BAD_ENTRY')
    prev_close 缺省时用 entry_idx-1 收盘。
    """
    if entry_idx < 0 or entry_idx >= len(daily):
        return False, "BAD_ENTRY"
    pc = prev_close or (daily[entry_idx - 1]["c"] if entry_idx >= 1 else ep)
    if pc and daily[entry_idx]["o"] >= pc * 1.095:
        return False, "SKIP_LIMIT_UP"
    if ep <= 0 or sl >= ep:
        return False, "BAD_ENTRY"
    return True, None


def is_suspended(px_info):
    """停牌判定：Sina 成交量=0 → 停牌无法成交（与 paper_sim 一致）。"""
    vol = (px_info or {}).get("vol")
    return vol == 0


def is_limit_up(px_info, side="buy"):
    """涨跌停判定（主板 10% 近似）。buy 触及涨停无法买入；sell 触及跌停无法卖出。"""
    px = (px_info or {}).get("px")
    prev = (px_info or {}).get("prev") or 0
    if not px or prev <= 0:
        return False
    chg = px / prev - 1
    return chg >= 0.095 if side == "buy" else chg <= -0.095


def simulate(daily, entry_idx, ep, sl, tp1=None, tp2=None, max_hold=None,
             partial_tp1=0.0, stop_to_be=False, prev_close=None, track_after_tp1=False):
    """统一逐 bar 执行模拟（回测/纸面共用）。

    返回 dict: {reason, exit_price, hold_bars, mfe_pct, mae_pct, mfe_r, mae_r,
                skipped, realized_partial}
    reason: TP_STRUCTURAL / TP1 / TP2_RUNNER / SL_HIT / SL_GAP / TIME_STOP / SKIP_LIMIT_UP
    """
    ok, skip = entry_ok(daily, entry_idx, ep, sl, prev_close)
    if not ok:
        return {"reason": skip, "exit_price": ep, "hold_bars": 0,
                "mfe_pct": 0.0, "mae_pct": 0.0, "mfe_r": 0.0, "mae_r": 0.0,
                "skipped": True, "realized_partial": 0.0}
    max_hold = max_hold or MAX_HOLD_DEFAULT
    risk = ep - sl
    if risk <= 0:
        return {"reason": "BAD_ENTRY", "exit_price": ep, "hold_bars": 0,
                "mfe_pct": 0.0, "mae_pct": 0.0, "mfe_r": 0.0, "mae_r": 0.0,
                "skipped": True, "realized_partial": 0.0}
    exit_price, reason, hold = ep, "TIME_STOP", 0
    remaining = 1.0
    realized = 0.0
    mfe = -999.0
    mae = 999.0
    be_active = False
    last_sl = sl
    for k in range(entry_idx + 1, min(len(daily), entry_idx + max_hold + 1)):
        bb = daily[k]
        hold += 1
        hi, lo, cl, op = bb["h"], bb["l"], bb["c"], bb["o"]
        mfe = max(mfe, (hi / ep - 1))
        mae = min(mae, (lo / ep - 1))
        stop = (ep if be_active else last_sl)
        # 跳空低开穿越止损 → 按开盘价（保守）
        if op < stop:
            exit_price, reason = op, "SL_GAP"
            realized += remaining * (op / ep - 1) * 100
            remaining = 0
            break
        if lo <= stop and hi >= (tp1 or tp2 or 0) and not be_active and partial_tp1 > 0:
            # 同K线 SL/TP 冲突 → SL 优先（保守，F16）
            exit_price, reason = stop, "SL_HIT"
            realized += remaining * (stop / ep - 1) * 100
            remaining = 0
            break
        if lo <= stop:
            exit_price, reason = stop, ("BE" if be_active else "SL_HIT")
            realized += remaining * (stop / ep - 1) * 100
            remaining = 0
            break
        # TP1 部分止盈（若启用）——触发后进入 runner 追踪（无论是否移保本）
        if not be_active and partial_tp1 > 0 and tp1 and hi >= tp1:
            realized += partial_tp1 * (tp1 / ep - 1) * 100
            remaining = 1.0 - partial_tp1
            be_active = True
            exit_price = tp1
            if stop_to_be:
                last_sl = ep
            continue
        # TP2 runner（若启用）
        if be_active and tp2 and hi >= tp2:
            realized += remaining * (tp2 / ep - 1) * 100
            remaining = 0
            exit_price, reason = tp2, "TP2_RUNNER"
            break
        # 单一结构 TP（调用方显式传 tp2）
        if not tp1 and tp2 and hi >= tp2:
            exit_price, reason = tp2, "TP_STRUCTURAL"
            realized += remaining * (tp2 / ep - 1) * 100
            remaining = 0
            break
        exit_price = cl
    if remaining > 0:
        last = daily[min(len(daily), entry_idx + max_hold) - 1]["c"]
        realized += remaining * (last / ep - 1) * 100
        reason = "TIME_STOP"
        exit_price = last
    gross = realized  # 已含分批
    return {"reason": reason, "exit_price": exit_price, "hold_bars": hold,
            "mfe_pct": (mfe * 100) if mfe != -999 else 0.0,
            "mae_pct": (mae * 100) if mae != 999 else 0.0,
            "mfe_r": (mfe * ep / risk) if mfe != -999 else 0.0,
            "mae_r": (mae * ep / risk) if mae != 999 else 0.0,
            "skipped": False, "realized_partial": gross,
            "net_pnl_pct": round(gross - FEE, 4)}
