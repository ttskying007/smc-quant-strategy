# -*- coding: utf-8 -*-
"""core/portfolio.py —— 组合与风控层（审计 G24 / 蓝图 D7）
初始资金、风险预算仓位、最大持仓/板块分散/开仓节流、权益曲线/MDD/Calmar、
月度贡献集中度(HHI)。让"年化 +294%"之类的数字有组合上下文。
"""
import statistics


def position_size(equity, risk_budget=0.01, entry=None, stop=None):
    """风险预算仓位：仓位 = equity×风险预算 / (入场−止损)。"""
    if not (entry and stop and entry > stop):
        return 0.0
    risk_px = entry - stop
    return equity * risk_budget / risk_px


def throttle_open(daily_opens, sector_counts, max_positions=10, max_sector=3,
                  max_daily_opens=5):
    """开仓节流：最大持仓 / 同板块≤N / 单日新开≤M。返回是否允许开仓。"""
    if len([p for p in daily_opens if p]) >= max_positions:
        return False, "MAX_POSITIONS"
    if any(v >= max_sector for v in sector_counts.values()):
        return False, "MAX_SECTOR"
    if len(daily_opens) >= max_daily_opens:
        return False, "MAX_DAILY_OPEN"
    return True, "OK"


def equity_curve(pnl_pcts, position_weights=None):
    """权益曲线：逐笔复利（等权或按仓位权重）。返回净值列表。"""
    eq = [1.0]
    for i, p in enumerate(pnl_pcts):
        w = position_weights[i] if position_weights else 1.0
        eq.append(eq[-1] * (1 + w * p / 100))
    return eq


def max_drawdown(eq):
    """最大回撤（净值序列）。返回 (mdd, peak_idx, trough_idx)。"""
    peak = -1e9
    peak_i = 0
    mdd = 0.0
    t_i = 0
    for i, v in enumerate(eq):
        if v > peak:
            peak = v
            peak_i = i
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > mdd:
            mdd = dd
            t_i = i
    return mdd, peak_i, t_i


def calmar(eq, years=3.0):
    """Calmar = 年化收益 / 最大回撤。"""
    if len(eq) < 2:
        return 0.0
    ann = (eq[-1] / eq[0]) ** (1 / max(years, 1e-9)) - 1
    mdd, _, _ = max_drawdown(eq)
    return ann / mdd if mdd > 0 else 0.0


def hhi(values):
    """集中度 Herfindahl：Σ(份额²)。月度收益贡献 <0.15 视为分散。"""
    tot = sum(abs(v) for v in values)
    if tot <= 0:
        return 0.0
    return sum((abs(v) / tot) ** 2 for v in values)


def monthly_contribution(pnl_pcts, months):
    """月度收益贡献（去月度聚合）+ HHI。"""
    from collections import defaultdict
    m = defaultdict(float)
    for p, mo in zip(pnl_pcts, months):
        m[mo] += p
    vals = [m[k] for k in sorted(m)]
    return vals, hhi(vals)
