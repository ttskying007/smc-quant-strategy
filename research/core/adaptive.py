# -*- coding: utf-8 -*-
"""core/adaptive.py —— 迭代四：股票/周期/市场状态自适应参数解析器
蓝图：不同 A 股股票用不同参数档位（流动性/波动率分层），只用过去窗口估计，
不满足样本数回退到全市场档位；所有动态参数有上下限；档位记录在日志/manifest。
"""
import statistics


def _atr_pct(daily, i, n=20):
    if i < n:
        return None
    vals = []
    for k in range(i - n + 1, i + 1):
        if k < 1:
            continue
        tr = max(daily[k]["h"] - daily[k]["l"],
                 abs(daily[k]["h"] - daily[k - 1]["c"]),
                 abs(daily[k]["l"] - daily[k - 1]["c"]))
        if daily[k]["c"] > 0:
            vals.append(tr / daily[k]["c"])
    return statistics.mean(vals) if vals else None


def _turnover_pct(daily, i, n=20):
    """用成交量近似流动性档（无股本时用量/价中位；有 volume 即可）。"""
    if i < n:
        return None
    vals = []
    for k in range(i - n + 1, i + 1):
        v = daily[k].get("v") or 0
        c = daily[k]["c"] or 1
        if v > 0:
            vals.append(v * c)  # 近似成交额
    return statistics.mean(vals) if vals else None


def vol_bucket(atr_pct):
    """波动率档：ATR% <2% 低 / 2-4% 中 / >4% 高。"""
    if atr_pct is None:
        return "default"
    if atr_pct < 0.02:
        return "low"
    if atr_pct < 0.04:
        return "mid"
    return "high"


# 参数档位表：每档的参数（扫损ATR倍数/位移ATR/止损缓冲/最长持有）
# 依据：高波动股扫损/SL 需更宽（避免噪声扫损），低波动可用更紧
VOL_TABLE = {
    "low":   {"sweep_atr": 0.5, "disp_atr": 0.8, "sl_atr_buf": 0.5, "max_hold": 12, "sweep_floor": 0.003},
    "mid":   {"sweep_atr": 0.5, "disp_atr": 1.0, "sl_atr_buf": 0.5, "max_hold": 12, "sweep_floor": 0.003},
    "high":  {"sweep_atr": 0.7, "disp_atr": 1.0, "sl_atr_buf": 0.7, "max_hold": 10, "sweep_floor": 0.003},
    "default": {"sweep_atr": 0.5, "disp_atr": 1.0, "sl_atr_buf": 0.5, "max_hold": 12, "sweep_floor": 0.003},
}


def resolve_params(daily, i, min_hist=40):
    """解析某股某时点参数档位。过去窗口估计，无样本/异常回退 default。
    返回 (profile_name, params, diagnostics)。"""
    diag = {}
    atr_p = _atr_pct(daily, i, 20)
    bucket = vol_bucket(atr_p)
    diag["atr_pct"] = atr_p if atr_p is not None else None
    diag["vol_bucket"] = bucket
    params = dict(VOL_TABLE.get(bucket, VOL_TABLE["default"]))
    params["min_hist"] = min_hist
    return bucket, params, diag


def sweep_tol_for(daily, i, params):
    """按档位计算扫损容差 = max(floor, sweep_atr × ATR%)。"""
    from core.structure import atr_of
    a = atr_of(daily, i)
    if a is None or daily[i]["c"] <= 0:
        return params["sweep_floor"]
    return max(params["sweep_floor"], params["sweep_atr"] * a / daily[i]["c"])


def sl_for(daily, i, struct_low, ep, params):
    """结构止损 + 波动缓冲：SL = struct_low × (1 - sl_atr_buf×ATR%) 保守下移。"""
    from core.structure import atr_of
    a = atr_of(daily, i)
    if a is None or ep <= 0:
        return struct_low * 0.99
    buf = params["sl_atr_buf"] * a / ep
    return struct_low * (1 - min(buf, 0.03))  # 缓冲 ≤3%
