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


# ============================================================
# B4(2026-09-10, 第四轮遗留): 日推进组合引擎 —— DailyPortfolioEngine
# 旧 equity_curve 是逐笔复利, 不是组合回测器。本引擎按【交易日】推进:
#   每日: ①挂单撮合(限价/次日开盘, 涨停拒买/跌停拒卖) ②持仓按 SL/TP/时间退出
#         ③新订单准入(风控: 总暴露/单票/板块/日开仓/杀开关) ④T+1 锁定
# 现金守恒: cash + Σ持仓市值 ≡ equity(允许日内撮合误差 <1e-6)。
# 语义无前视: 撮合只用当日 bar(o/h/l/c), 决策只用当日之前信息。
# ============================================================
class DailyPortfolioEngine:
    """按交易日推进的组合回测器。

    参数:
      init_cash: 初始资金
      fee_pct / slippage_pct: 费率与滑点(%)
      max_total_exposure / max_single / max_daily_opens: 组合风控
      kill_daily_loss: 单日组合亏损超此比例 → 杀开关(次日停止开仓)
    用法:
      eng = DailyPortfolioEngine(1_000_000)
      eng.submit_order({code, signal_date, entry_limit, sl, tp, bars_max, position_pct})
      for each trading_day: eng.on_day(date8, market={code: {o,h,l,c,limit_up,limit_down,suspended}})
    """

    def __init__(self, init_cash=1_000_000.0, fee_pct=0.2, slippage_pct=0.1,
                 max_total_exposure=0.8, max_single=0.25, max_daily_opens=5,
                 kill_daily_loss=0.03, max_sector=3, kill_days=2):
        self.init_cash = float(init_cash)
        self.cash = float(init_cash)
        self.fee = fee_pct / 100.0
        self.slip = slippage_pct / 100.0
        self.max_total_exposure = max_total_exposure
        self.max_sector = max_sector            # V3-A P1-2: 行业集中度强制门
        self.kill_days = kill_days             # V3-A P0-3: kill 持续【交易日】数
        self.max_single = max_single
        self.max_daily_opens = max_daily_opens
        self.kill_daily_loss = kill_daily_loss
        self.orders = []            # 挂单 [{code, entry_limit, sl, tp, ...}]
        self.positions = {}         # code -> {entry_px, shares, sl, tp, bars_held, buy_day, cost}
        self.pending_orders = []    # 当日已提交未撮合
        self.daily_pnl = []         # 每日已实现+未实现盈亏记录
        self.equity_hist = []       # (date, equity)
        self.trade_log = []         # 已平仓 [{code, ret, hold_days, reason, day}]
        self.kill_until = None      # 兼容字段(已由 kill_trading_days 替代, 见 on_day ④)
        self.kill_trading_days = 0  # V3-A P0-3: 剩余禁开仓【交易日】数
        self.kill_events = []       # kill 触发记录
        self.cancelled_orders = []  # V3-A P1-3: TTL 过期撤单记录
        self.day_pnl = 0.0

    # ---- 工具 ----
    def _equity(self, market):
        mv = 0.0
        for code, p in self.positions.items():
            px = market.get(code, {}).get("c") or p["entry_px"]
            mv += px * p["shares"]
        return self.cash + mv

    def submit_order(self, o):
        """提交挂单(signal 生成日调用; 次日起撮合)。o: {code, entry_limit, sl, tp,
        position_pct, bars_max, valid_from(可选), cap_shares(可选: 成交量容量上限)}。
        cap_shares: 单一订单最多买入股数(容量约束) —— 仓位再大也截到该股数。"""
        if float(o.get("position_pct") or 0) > self.max_single:
            o = dict(o, position_pct=self.max_single)
        self.orders.append(dict(o))

    # ---- 每日推进 ----
    def on_day(self, d8, market, sector_of=None):
        """一个交易日的完整推进。market: {code: {o,h,l,c, limit_up(可选bool),
        limit_down(可选bool), suspended(可选bool)}}。sector_of: {code: 板块}。"""
        self.day_pnl = 0.0
        # V3-A P0-3: day_pnl 改为【权益日差异】(含未实现) —— 旧实现只累计平仓盈亏,
        # 持仓暴跌(未平仓)不触发 kill switch 的语义漏洞修复
        _eq_prev = self.equity_hist[-1][1] if self.equity_hist else self.init_cash
        # ① 持仓退出(T+1: buy_day==d8 不可卖)
        for code in list(self.positions.keys()):
            p = self.positions[code]
            m = market.get(code)
            if not m or m.get("suspended"):
                continue          # 停牌日不计持有(P0-2: 只数可交易日)
            sellable = p["buy_day"] != d8
            if not sellable:
                # T+1: 买入日 bars_held 保持 0(当日不计入持有交易日 —— P0-2 对齐)
                continue
            # 可卖日: bars_held+1 在【退出检查前】完成 —— 第N个持有日检查N>=bars_max
            p["bars_held"] += 1
            px_exit = None
            reason = None
            # 跌停不能卖(仍计持有日)
            if m.get("limit_down"):
                continue
            if m["l"] <= p["sl"]:
                px_exit = min(m["o"], p["sl"])   # 跳空低开按开盘
                px_exit = px_exit * (1 - self.slip)
                reason = "SL"
            elif p["tp"] and m["h"] >= p["tp"]:
                px_exit = max(m["o"], p["tp"])
                px_exit = px_exit * (1 - self.slip)
                reason = "TP"
            elif p["bars_held"] >= p.get("bars_max", 15):
                # V3-A P0-2 off-by-one 修复: bars_held 语义 = 已完整持有的交易日数
                # (fill 日=0, 次日=1...); bars_max=15 → 第 15 个持有日收盘退出,
                # 与 core.setup_exit(fi+max_bars) 黄金一致(黄金测试锁死)。
                px_exit = m["c"] * (1 - self.slip)
                reason = "TIME"
            if px_exit is not None:
                gross = px_exit * p["shares"]
                fee = gross * self.fee
                self.cash += gross - fee
                ret = (px_exit * (1 - 0) / p["entry_px"] - 1) - self.fee * 2  # 净收益近似
                self.day_pnl += (gross - fee - p["cost"])
                self.trade_log.append({"code": code, "day": d8, "reason": reason,
                                       "ret_pct": round(ret * 100, 3),
                                       "pnl_cash": round(gross - fee - p["cost"], 2),
                                       "hold_days": p["bars_held"]})
                del self.positions[code]
        # ② 挂单撮合(先到价先成; 涨停拒买/停牌跳过)
        filled_today = []
        for o in list(self.orders):
            vf = str(o.get("valid_from") or "")
            if vf and d8 < vf:
                continue
            code = o["code"]
            # 已持仓同票 → 跳过该单(不叠加、不覆盖 —— 同股并发仓位禁止)
            if code in self.positions:
                continue
            m = market.get(code)
            if not m or m.get("suspended"):
                continue
            # P1-3 订单 TTL: max_pending_days(默认5, 可交易日)过期撤单 —— Setup 只在
            # 自己有效窗口内有效, 禁止"一个月前的信号还在等触价"。
            # 计数法(不依赖日历): 订单自带 _pend_days, 每个可交易日 +1, 超 TTL 撤。
            mpd = int(o.get("max_pending_days") or 5)
            o["_pend_days"] = int(o.get("_pend_days", 0)) + 1
            if o["_pend_days"] > mpd:
                self.cancelled_orders.append({"code": code, "day": d8,
                                              "reason": "TTL_EXPIRED",
                                              "pending_days": o["_pend_days"]})
                self.orders.remove(o)
                continue
            if m.get("limit_up"):
                continue
            # 限价撮合 —— V3-A 执行语义锁死(第五轮审计 P0-1):
            # 触价: low <= entry_limit → 成交价 = min(open, entry_limit)(开盘更优按开盘)
            # fill_or_open=True 且未触价: 按【开盘价】成交(不是 entry_limit! 旧实现
            #   min(m['o'], entry_limit) 在 open>limit 且全天未触价时会伪造 limit 价成交
            #   —— 回测执行幻觉, 本轮修复)
            # 未触价且无 fill_or_open: 挂单继续等待(TTL 见 o['max_pending_days'])
            touched = m["l"] <= o["entry_limit"]
            if touched:
                px = min(m["o"], o["entry_limit"]) * (1 + self.slip)
            elif o.get("fill_or_open"):
                px = m["o"] * (1 + self.slip)          # 开盘兜底 = 真实开盘价
            else:
                continue                               # 未触价: 不成交(限价语义)
            # ---- 以下仅在确定成交价 px 后执行(风控准入) ----
            # P1-2 行业集中度强制门: sector_of 提供时, 单行业持仓 >= max_sector 拒新开仓
            if sector_of:
                sec = sector_of.get(code)
                if sec is not None:
                    held_secs = [sector_of.get(c) for c in self.positions]
                    if held_secs.count(sec) >= self.max_sector:
                        continue
            # P0-3 kill switch: 交易日推进(非自然日) —— 剩余禁开仓交易日 > 0 即拒
            if self.kill_trading_days > 0:
                continue
            equity = self._equity(market)
            pos_pct = float(o.get("position_pct") or 0)
            cur_exposure = 1 - (self.cash / equity) if equity else 0
            if cur_exposure + pos_pct > self.max_total_exposure:
                continue
            if len(filled_today) >= self.max_daily_opens:
                break
            shares = int(equity * pos_pct / px)
            # 容量上限: cap_shares 截断(成交量参与率约束)
            cap_sh = o.get("cap_shares")
            if cap_sh is not None:
                shares = min(shares, int(cap_sh))
            cost = shares * px
            fee = cost * self.fee
            if shares <= 0 or cost + fee > self.cash:
                continue
            self.cash -= cost + fee
            self.positions[code] = {"entry_px": px, "shares": shares,
                                    "sl": o.get("sl"), "tp": o.get("tp"),
                                    "bars_max": o.get("bars_max", 15),
                                    "bars_held": 0, "buy_day": d8,
                                    "cost": cost + fee}
            filled_today.append(code)
            self.orders.remove(o)
        # ③ 当日权益记录
        eq = self._equity(market)
        self.day_pnl = eq - _eq_prev                     # 权益日差异(含未实现)
        self.equity_hist.append((d8, round(eq, 2)))
        self.daily_pnl.append({"day": d8, "pnl": self.day_pnl, "equity": round(eq, 2)})
        # ④ 杀开关 —— V3-A P0-3: 交易日推进(非自然日)。
        #   触发日 → 之后 self.kill_days(默认2)个【交易日】禁开仓, 逐日递减。
        if self.kill_trading_days > 0:
            self.kill_trading_days -= 1
        if self.day_pnl / max(eq, 1e-9) <= -self.kill_daily_loss:
            self.kill_trading_days = self.kill_days    # e.g. 2 → 接下来2个交易日
            self.kill_events.append({"day": d8, "day_pnl": round(self.day_pnl, 2)})
        return eq

    # ---- 结果 ----
    def summary(self):
        eqs = [e for _, e in self.equity_hist]
        mdd, _, _ = max_drawdown(eqs) if len(eqs) >= 2 else (0, 0, 0)
        wins = [t for t in self.trade_log if t["ret_pct"] > 0]
        losses = [t for t in self.trade_log if t["ret_pct"] <= 0]
        pf = (sum(t["pnl_cash"] for t in wins) / abs(sum(t["pnl_cash"] for t in losses))
              if losses and sum(t["pnl_cash"] for t in losses) != 0 else None)
        return {"init_cash": self.init_cash,
                "final_equity": eqs[-1] if eqs else self.init_cash,
                "total_return_pct": round(((eqs[-1] / self.init_cash) - 1) * 100, 2) if eqs else 0,
                "mdd_pct": round(mdd * 100, 2),
                "n_trades": len(self.trade_log),
                "win_rate": round(len(wins) / len(self.trade_log) * 100, 1) if self.trade_log else None,
                "pf": round(pf, 2) if pf else None,
                "n_open_positions": len(self.positions),
                "avg_hold_days": (round(sum(t["hold_days"] for t in self.trade_log) / len(self.trade_log), 1)
                                  if self.trade_log else None)}

    def conservation_ok(self, market, tol=1e-6):
        """现金守恒审计: cash + Σ持仓市值 ≡ 当前权益。"""
        mv = sum((market.get(c, {}).get("c") or p["entry_px"]) * p["shares"]
                 for c, p in self.positions.items())
        eq = self.cash + mv
        # 初始资金 - 累计已实现盈亏 - 现金 = 应为0(全现金时)
        return eq >= 0 and abs(self.cash + mv - eq) < tol
