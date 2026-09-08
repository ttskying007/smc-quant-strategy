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


# ---------------- 复审 P1-5: 组合级风险控制 ----------------
def portfolio_exposure_check(positions, max_total_exposure=0.8, max_single=0.25):
    """总暴露检查：Σ position_pct ≤ max_total_exposure；单票 ≤ max_single。
    positions: [{code, position_pct}]。返回 (ok, reason, total_exposure)。"""
    total = sum(float(p.get("position_pct") or 0) for p in positions)
    worst = max((float(p.get("position_pct") or 0) for p in positions), default=0)
    if worst > max_single:
        return False, f"单票超限 {worst:.1%}>{max_single:.0%}", total
    if total > max_total_exposure:
        return False, f"总暴露超限 {total:.1%}>{max_total_exposure:.0%}", total
    return True, "OK", total


def industry_concentration_check(positions, industry_of, max_industry=0.4):
    """行业集中度：任一行业暴露 ≤ max_industry。industry_of: {code: industry}。"""
    from collections import defaultdict
    by_ind = defaultdict(float)
    for p in positions:
        ind = industry_of.get(p.get("code"), "UNKNOWN")
        by_ind[ind] += float(p.get("position_pct") or 0)
    worst_ind = max(by_ind.items(), key=lambda kv: kv[1], default=("", 0))
    if worst_ind[1] > max_industry:
        return False, f"行业 {worst_ind[0]} 暴露 {worst_ind[1]:.1%}>{max_industry:.0%}", dict(by_ind)
    return True, "OK", dict(by_ind)


def kill_switch(recent_pnls, window="daily", daily_loss=-0.03, weekly_loss=-0.06,
                consecutive_loss=-5):
    """kill switch：连续亏损 / 日亏损 / 周亏损 超限 → 停止开仓。
    recent_pnls: 最近已平仓净收益列表(按时间序, 单位=小数)。
    返回 (triggered, reason, detail)。"""
    if not recent_pnls:
        return False, "", {"window": window}
    if window == "consecutive":
        streak = 0
        for p in reversed(recent_pnls):
            if p < 0:
                streak += 1
            else:
                break
        if streak >= consecutive_loss:
            return True, f"连续亏损 {streak} 笔 ≥{consecutive_loss}", {"streak": streak}
    elif window == "daily":
        if sum(recent_pnls[-20:]) <= daily_loss:
            return True, f"近20笔合计 {sum(recent_pnls[-20:]):.1%} ≤{daily_loss:.0%}", {"sum": sum(recent_pnls[-20:])}
    elif window == "weekly":
        if sum(recent_pnls[-100:]) <= weekly_loss:
            return True, f"近100笔合计 {sum(recent_pnls[-100:]):.1%} ≤{weekly_loss:.0%}", {"sum": sum(recent_pnls[-100:])}
    return False, "", {}


def idempotent_order_check(existing_orders, new_order):
    """订单幂等：同 code+signal_date+order_type 已存在 → 拒绝重复提交。
    existing_orders: [{code, signal_date, order_type}]。new_order: dict。返回 (dup, reason)。"""
    for o in existing_orders:
        if (o.get("code") == new_order.get("code")
                and o.get("signal_date") == new_order.get("signal_date")
                and o.get("order_type") == new_order.get("order_type")):
            return True, f"重复订单: {new_order.get('code')} {new_order.get('signal_date')} {new_order.get('order_type')}"
    return False, ""


def gap_risk_check(position, gap_pct):
    """跳空损失检查：隔夜 gap 造成的额外风险。position: {position_pct, sl}。
    gap_pct: 跳空比例(小数, 负=向下跳空)。返回 (gap_loss_pct_of_account, breached)。"""
    pos = float(position.get("position_pct") or 0)
    # 跳空击穿止损 → 以开盘价成交（缺口损失 = gap_pct × 仓位）
    if gap_pct < 0:
        loss = abs(gap_pct) * pos
        return loss, loss > pos * 0.5  # 缺口损失超过仓位的50%视为 breach
    return 0.0, False
