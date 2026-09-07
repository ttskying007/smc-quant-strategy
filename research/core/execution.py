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


def limit_pct_for(code):
    """FIX(2026-09-05, 审计 G18): 涨跌停幅度按板块/代码规则。
    主板(60x/000/001/002) 10% | 创业板(300/301) 20% | 科创板(688) 20% |
    北交所(4/8/9开头,BJ) 30% | ST 5%（由调用方在名称中判定, 此处按代码）。
    返回 0.10 / 0.20 / 0.30。"""
    s = str(code or "")
    if s.startswith(("300", "301", "688")):
        return 0.20
    if s.startswith(("4", "8", "9")) and len(s) == 6:
        return 0.30
    return 0.10


def entry_ok(daily, entry_idx, ep, sl, prev_close=None, code=None):
    """A 股入场约束（F08/G18）：
    ① 一字涨停开盘买不到 → 返回 (False, 'SKIP_LIMIT_UP')（按板块涨跌停幅度）
    ② 入场价无效 → (False, 'BAD_ENTRY')
    prev_close 缺省时用 entry_idx-1 收盘。
    """
    if entry_idx < 0 or entry_idx >= len(daily):
        return False, "BAD_ENTRY"
    pc = prev_close or (daily[entry_idx - 1]["c"] if entry_idx >= 1 else ep)
    _lmt = limit_pct_for(code) if code else 0.10
    if pc and daily[entry_idx]["o"] >= pc * (1 + _lmt - 0.005):
        return False, "SKIP_LIMIT_UP"
    if ep <= 0 or sl >= ep:
        return False, "BAD_ENTRY"
    return True, None


def is_suspended(px_info):
    """停牌判定：Sina 成交量=0 → 停牌无法成交（与 paper_sim 一致）。"""
    vol = (px_info or {}).get("vol")
    return vol == 0


def is_limit_up(px_info, side="buy", code=None):
    """涨跌停判定（FIX G18: 按板块幅度）。buy 触及涨停无法买入；sell 触及跌停无法卖出。"""
    px = (px_info or {}).get("px")
    prev = (px_info or {}).get("prev") or 0
    if not px or prev <= 0:
        return False
    chg = px / prev - 1
    _lmt = limit_pct_for(code) if code else 0.10
    _thr = _lmt - 0.005  # 略低于停板价判定（触及即不可成交）
    return chg >= _thr if side == "buy" else chg <= -_thr


def simulate(daily, entry_idx, ep, sl, tp1=None, tp2=None, max_hold=None,
             partial_tp1=0.0, stop_to_be=False, prev_close=None, track_after_tp1=False,
             code=None, tp3=None):
    """统一逐 bar 执行模拟（回测/纸面共用）。

    返回 dict: {reason, exit_price, hold_bars, mfe_pct, mae_pct, mfe_r, mae_r,
                skipped, realized_partial}
    reason: TP_STRUCTURAL / TP1 / TP2_RUNNER / TP3_RUNNER / SL_HIT / SL_GAP / TIME_STOP / SKIP_LIMIT_UP
    FIX(2026-09-08, 第七轮): 新增 tp3 可选 runner（gen_v20f 事件腿 TP3 语义并入统一内核，
    消除回测事件腿的平行退出实现）。tp3 触发优先于 TIME_STOP，在 TP2 之后检查。
    """
    ok, skip = entry_ok(daily, entry_idx, ep, sl, prev_close, code)
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
        # FIX(2026-09-05, 审计 G15): 结构追踪 —— TP1 后 SL 上移至"最近已确认 swing low − 0.3ATR"
        # （不低于保本），减少"MFE≥1R 却 TIME_STOP 卖飞"；需 run_sim 传入 track_after_tp1
        if be_active and track_after_tp1 and k >= 3:
            _trail = ep
            _n = 0
            for _j in range(k - 1, max(0, k - 8), -1):
                if (_j - 1 >= 0 and _j + 1 < len(daily)
                        and daily[_j]["l"] < daily[_j - 1]["l"] and daily[_j]["l"] <= daily[_j + 1]["l"]):
                    _atr_k = 0.0
                    for _q in range(max(0, _j - 14), _j):
                        _atr_k += max(daily[_q]["h"] - daily[_q]["l"],
                                      abs(daily[_q]["h"] - daily[_q - 1]["c"]),
                                      abs(daily[_q]["l"] - daily[_q - 1]["c"]))
                    _atr_k = _atr_k / max(1, min(14, _j))
                    _cand = daily[_j]["l"] - 0.3 * _atr_k
                    if _cand > _trail:
                        _trail = _cand
                    _n += 1
                    if _n >= 2:
                        break
            last_sl = max(last_sl, _trail)
        # FIX(2026-09-08, 审计 P1-1): 追踪止损上移后必须生效。
        # 原 `stop = ep if be_active else last_sl` 在 TP1 后无论 last_sl 是否被结构抬高，
        # 止损恒等于保本(ep)，导致结构追踪(track_after_tp1)白算、浮盈回吐。
        # 正确：TP1 后止损 = max(保本, 结构追踪上移位) —— 追踪更高时用追踪，否则至少保本。
        stop = (max(ep, last_sl) if be_active else last_sl)
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
        # FIX(2026-09-08, 第七轮): TP3 runner（gen_v20f 事件腿语义并入；
        # 与 TP2 互斥 —— TP2 已 break，此处仅当 tp2 未触发而 tp3 直达时（tp2<tp3 且盘中越级））
        if be_active and tp3 and hi >= tp3 and (not tp2 or tp3 > tp2):
            realized += remaining * (tp3 / ep - 1) * 100
            remaining = 0
            exit_price, reason = tp3, "TP3_RUNNER"
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


# ---------------- 统一执行三函数（审计 P0-4）----------------
# 回测（simulate，逐 bar）与纸面（实时快照）共用同一套语义：
#   plan_order  —— 信号只生成挂单计划（valid_from / 参考价），不写死成交价
#   try_fill    —— 用实时/下一日市场快照撮合（涨跌停/停牌/valid_from 由本核心统一判定）
#   try_exit    —— 用实时快照判离场（SL/BE 优先 → TP1/TP2 → 时间止损最后），
#                  与 simulate 的逐 bar 判定顺序完全一致（FIX P0-4: 消除回测/纸面口径分裂）

def plan_order(signal, asof_date=None):
    """信号 → 挂单计划。signal 需含: code/name/signal_date/entry_ref(reference_price)/sl/tp。
    返回 PendingOrder dict: 不含实际成交价，只含 valid_from + 计划参考。"""
    code = str(signal.get("code") or "")
    entry_ref = float(signal.get("entry_ref") or signal.get("reference_price") or 0)
    sl = float(signal.get("sl") or 0)
    tp = float(signal.get("tp") or 0)
    sig_date = str(signal.get("signal_date") or "").replace("-", "")
    if not (code and entry_ref > 0 and sl > 0 and sl < entry_ref and tp > entry_ref):
        return {"ok": False, "reason": "BAD_SIGNAL", "code": code}
    return {
        "ok": True, "code": code, "name": signal.get("name") or code,
        "signal_date": sig_date,
        "entry_mode": signal.get("entry_mode") or "next_open",
        "reference_price": round(entry_ref, 3),
        "planned_sl": round(sl, 3), "planned_tp": round(tp, 3),
        "valid_from": signal.get("valid_from") or "",  # 由调用方交易日历填
        "asof": asof_date or "", "status": "PENDING_ORDER",
        "actual_filled_price": None, "filled_at": None,
    }


def try_fill(order, market_snapshot):
    """挂单 + 市场快照 → FillResult。
    market_snapshot: {px, prev, open, vol}（Sina 实时口径）。
    统一判定（顺序固定）：停牌 → 涨跌停(按板块) → 未到 valid_from → 撮合。"""
    snap = market_snapshot or {}
    code = order.get("code") or ""
    px, prev, opn, vol = snap.get("px"), snap.get("prev"), snap.get("open"), snap.get("vol")
    if not px or px <= 0:
        return {"filled": False, "why": "NO_PRICE"}
    if is_suspended(snap):
        return {"filled": False, "why": "SUSPENDED"}
    if is_limit_up(snap, side="buy", code=code):
        return {"filled": False, "why": "LIMIT_UP"}
    vf = str(order.get("valid_from") or "")
    today = str(snap.get("today") or "")
    if vf and today and today < vf:
        return {"filled": False, "why": "NOT_YET_VALID"}
    mode = order.get("entry_mode") or "next_open"
    if mode == "retrace":
        # 回踩限价：回落到参考价成交；否则当日开盘兜底
        if px <= float(order.get("reference_price") or 0):
            fill_px = float(order["reference_price"]) * (1 + SLIPPAGE)
        elif opn and opn > 0:
            fill_px = opn * (1 + SLIPPAGE)
        else:
            return {"filled": False, "why": "WAIT_RETRACE"}
    else:  # next_open
        if not (opn and opn > 0):
            return {"filled": False, "why": "NO_OPEN"}
        fill_px = opn * (1 + SLIPPAGE)
    return {"filled": True, "price": round(fill_px, 3),
            "sl": order.get("planned_sl"), "tp": order.get("planned_tp")}


def try_exit(position, market_snapshot):
    """持仓 + 实时快照 → ExitResult。判定顺序与 simulate 逐 bar 完全一致：
    ① SL/BE（含 T+1 锁定：当日买入不可卖）→ ② TP1 部分平 → ③ TP2 全平 → ④ 时间止损。
    position: {code, filled_price(filled), sl, tp, tp1, tp2, tp1_hit, filled_at, asof_bars}
    market_snapshot: {px, today, bars_since_fill}"""
    snap = market_snapshot or {}
    code = position.get("code") or ""
    px = snap.get("px")
    if not px or px <= 0:
        return {"exit": False, "why": "NO_PRICE"}
    if is_suspended(snap):
        return {"exit": False, "why": "SUSPENDED"}
    if is_limit_up(snap, side="sell", code=code):
        return {"exit": False, "why": "LIMIT_DOWN_SELL"}
    ep = float(position.get("filled_price") or position.get("filled") or 0)
    if ep <= 0:
        return {"exit": False, "why": "BAD_POSITION"}
    # T+1：买入当日不可卖
    today = str(snap.get("today") or "")
    if today and str(position.get("filled_at") or "")[:10].replace("-", "") == today.replace("-", ""):
        return {"exit": False, "why": "T1_LOCKED"}
    sl = float(position.get("sl") or 0)
    tp1 = float(position.get("tp1") or 0)
    tp2 = float(position.get("tp2") or position.get("tp") or 0)
    tp1_hit = bool(position.get("tp1_hit"))
    # ① active SL（TP1 后保本）—— 与 simulate 一致
    active_sl = sl if not tp1_hit else max(ep, sl)
    if active_sl and px <= active_sl:
        return {"exit": True, "reason": "BE" if (tp1_hit and abs(active_sl - ep) < 1e-6) else "SL_HIT",
                "price": round(px * (1 - SLIPPAGE), 3)}
    # ② TP1 部分平（未触过）
    if not tp1_hit and tp1 and px >= tp1:
        return {"exit": False, "partial": "TP1", "new_state": {"tp1_hit": True, "sl": ep}}
    # ③ TP2 全平
    if tp1_hit and tp2 and px >= tp2:
        return {"exit": True, "reason": "TP2_RUNNER", "price": round(px * (1 - SLIPPAGE), 3)}
    # ④ 时间止损（未触 TP1 且超 max_hold）—— 最后判定
    bars = snap.get("bars_since_fill")
    if (not tp1_hit) and bars is not None and int(bars) >= (getattr(CFG, "MAX_HOLD", 12)):
        return {"exit": True, "reason": "TIME_STOP", "price": round(px * (1 - SLIPPAGE), 3)}
    return {"exit": False, "why": "HOLD"}
