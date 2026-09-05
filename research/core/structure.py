# -*- coding: utf-8 -*-
"""core/structure.py —— SMC 结构核心（审计 F14 收敛）
统一摆动点 / ATR / 阶段识别实现，供 wdh_engine、paper_sim、scanner 共用。
"""
import datetime as _dt


# ---------------- 摆动点（含确认窗口，防未来数据 F04）----------------
def is_swing_low(ks, j, pivot=3):
    if j < pivot or j + pivot >= len(ks):
        return False
    lo = ks[j]["l"]
    return (lo < min(ks[k]["l"] for k in range(j - pivot, j))
            and lo <= min(ks[k]["l"] for k in range(j + 1, j + pivot + 1)))


def is_swing_high(ks, j, pivot=3):
    if j < pivot or j + pivot >= len(ks):
        return False
    hi = ks[j]["h"]
    return (hi > max(ks[k]["h"] for k in range(j - pivot, j))
            and hi >= max(ks[k]["h"] for k in range(j + 1, j + pivot + 1)))


def confirmed_swing_lows(ks, up_to_idx, pivot=3):
    """返回 [j, ...]：在 up_to_idx 时刻已确认的摆动低点（j + pivot <= up_to_idx，防未来）。"""
    out = []
    for j in range(pivot, up_to_idx - pivot + 1):
        if j + pivot <= up_to_idx and is_swing_low(ks, j, pivot):
            out.append(j)
    return out


def confirmed_swing_highs(ks, up_to_idx, pivot=3):
    out = []
    for j in range(pivot, up_to_idx - pivot + 1):
        if j + pivot <= up_to_idx and is_swing_high(ks, j, pivot):
            out.append(j)
    return out


# ---------------- ATR ----------------
def atr_of(daily, i, n=14):
    if i < n:
        return None
    trs = []
    for k in range(i - n + 1, i + 1):
        if k < 1:
            continue
        trs.append(max(daily[k]["h"] - daily[k]["l"],
                       abs(daily[k]["h"] - daily[k - 1]["c"]),
                       abs(daily[k]["l"] - daily[k - 1]["c"])))
    return sum(trs) / len(trs) if trs else None


def sweep_tol_of(daily, i, base=0.003):
    _a = atr_of(daily, i)
    if _a is None or daily[i]["c"] <= 0:
        return base
    return max(base, 0.5 * _a / daily[i]["c"])


# ---------------- 阶段识别 ----------------
def stage_and_deep(bs, i):
    """回测口径（全市场硬阈值，保留兼容）。"""
    if i < 91:
        return None, False
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    if ret60 < -0.15 and vt60 < 0.9:
        return "ACCUM", deep
    if ret60 > 0.30 and vt60 > 1.3:
        return "DISTRIB", deep
    if ret60 > 0.20 and vt60 > 1.1:
        return "MARKUP", deep
    if ret60 > 0:
        return "UPTREND", deep
    return "DOWNTREND", deep


def stage_and_deep_quantile(bs, i):
    """每股自身 250 根滚动分位（审计 F12），返回 (stage, deep)。"""
    if i < 91:
        return None, False
    w90 = bs[i - 90:i]
    w60 = bs[i - 60:i]
    w20 = bs[i - 20:i]
    ret60 = w60[-1]["c"] / w60[0]["c"] - 1
    ret90 = w90[-1]["c"] / w90[0]["c"] - 1
    v20 = sum(b["v"] for b in w20) / len(w20)
    v60 = sum(b["v"] for b in w60) / len(w60)
    v90 = sum(b["v"] for b in w90) / len(w90)
    vt60 = v20 / v60 if v60 else 1
    vt90 = v20 / v90 if v90 else 1
    deep = ret90 < -0.20 and vt90 < 0.75
    hist_ret = []
    hist_vt = []
    for k in range(max(90, i - 250), i):
        w60k = bs[k - 60:k]
        w20k = bs[k - 20:k]
        if len(w60k) < 60 or len(w20k) < 20:
            continue
        r60 = w60k[-1]["c"] / w60k[0]["c"] - 1
        v2 = sum(x["v"] for x in w20k) / len(w20k)
        v6 = sum(x["v"] for x in w60k) / len(w60k)
        hist_ret.append(r60)
        hist_vt.append(v2 / v6 if v6 else 1)
    if len(hist_ret) < 30:
        return None, deep
    ret_pct = sum(1 for x in hist_ret if x < ret60) / len(hist_ret)
    vt_pct = sum(1 for x in hist_vt if x < vt60) / len(hist_vt)
    if ret_pct < 0.25 and vt_pct < 0.40:
        return "ACCUM", deep
    if ret_pct > 0.75 and vt_pct > 0.70:
        return "MARKUP", deep
    if ret_pct > 0.55:
        return "UPTREND", deep
    if ret_pct < 0.40:
        return "DOWNTREND", deep
    return "UPTREND", deep


def weekly_trend_of(bs, i):
    """真实自然周聚合周线趋势（审计 P3）。"""
    week_map = {}
    for k in range(i, -1, -1):
        t = str(bs[k]["t"])
        try:
            iso = _dt.datetime.strptime(t[:8], "%Y%m%d").isocalendar()[:2]
        except Exception:
            continue
        week_map.setdefault(iso, bs[k]["c"])
        if len(week_map) >= 20:
            break
    week_close = [week_map[k] for k in sorted(week_map.keys())]
    if len(week_close) < 12:
        return None
    ma10 = sum(week_close[-10:]) / 10
    ma_prev = sum(week_close[-12:-2]) / 10
    return "up" if ma10 > ma_prev else "down"
