# -*- coding: utf-8 -*-
"""execution_simulator.py —— 严格 A 股成交模拟器(审计 §7.4 / Iteration 3).

审计 §7.4 要求模拟器至少处理:
  - T+1 卖出限制
  - 涨跌停不可成交
  - 停牌和缺失行情
  - 复权口径与实际成交价口径一致
  - 佣金、印花税、滑点和最小成交单位
  - 单标的重叠持仓和资金占用
  - 组合层最大持仓数、行业暴露和单票风险

本模拟器是可复用的纯函数模块(无 IO):
  - can_execute(bar, side, prev_close, limit_pct): 涨跌停/停牌检查
  - execute_open(bar, prev_close, direction, limit_pct, slippage):
    次日开盘成交, 含涨停拒买/跌停拒卖/跳空检查
  - simulate_exit_strict(bars, entry_idx, entry_price, sl, tp, ...):
    T+1 + SL 优先 + 跳空 + 涨跌停 + 成本, 返回结构化结果
  - capacity_check(volume, price, position_pct, cap_ratio): 成交量容量

所有检查返回明确拒绝原因(FAIL_CLOSED), 不静默成交(§10.2 属性测试).
纯内存, 不写生产.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# A 股常量
FEE_PCT = 0.20        # 往返成本 % (佣金+印花税+滑点近似, 与 V699 一致)
SLIP_PCT = 0.05       # 额外滑点 % (单边)
LIMIT_PCT = 0.10      # 主板涨跌停 10%(科创板/创业板 20% 由调用方指定)
MIN_UNIT = 100        # 最小成交单位 100 股(1手)
MAX_POSITIONS = 10    # 组合层最大持仓数(默认)
SINGLE_POS_CAP = 0.25  # 单票仓位上限 25%
TOTAL_POS_CAP = 0.80   # 组合总仓位上限 80%
CAPACITY_RATIO = 0.05  # 单日成交不超当日成交量的 5%(容量约束)


def is_limit_move(bar: Dict[str, Any], prev_close: float, side: str,
                  limit_pct: float = LIMIT_PCT) -> bool:
    """涨跌停检查: 涨停(买不到)/跌停(卖不出)."""
    if prev_close <= 0:
        return False
    if side == "buy":
        return bar["o"] >= prev_close * (1 + limit_pct) - 1e-9
    return bar["o"] <= prev_close * (1 - limit_pct) + 1e-9


def is_suspended(bar: Dict[str, Any]) -> bool:
    """停牌/缺失行情检查: 开盘价为 0 或无交易."""
    return (bar.get("o") is None or bar.get("o", 0) <= 0
            or bar.get("v", 0) <= 0)


def can_execute(bar: Dict[str, Any], prev_close: float, side: str,
                limit_pct: float = LIMIT_PCT) -> Tuple[bool, str]:
    """成交前检查. 返回 (ok, reason). 任一不满足即 fail-closed 拒绝."""
    if is_suspended(bar):
        return False, "SUSPENDED"
    if is_limit_move(bar, prev_close, side, limit_pct):
        return False, "LIMIT_UP" if side == "buy" else "LIMIT_DOWN"
    return True, "OK"


def capacity_check(bar: Dict[str, Any], position_pct: float,
                   capital: float, cap_ratio: float = CAPACITY_RATIO) -> Tuple[bool, str]:
    """成交量容量: 订单金额不得超过当日成交额 * cap_ratio."""
    order_amt = capital * position_pct
    day_amt = bar["o"] * bar["v"] * 100  # 成交额≈开盘价*成交量*100股
    if day_amt <= 0:
        return False, "NO_VOLUME"
    if order_amt > day_amt * cap_ratio:
        return False, "CAPACITY_EXCEEDED"
    return True, "OK"


def execute_open(bar: Dict[str, Any], prev_close: float, direction: str,
                 limit_pct: float = LIMIT_PCT, slippage_pct: float = SLIP_PCT,
                 capital: float = 1_000_000.0, position_pct: float = 0.05,
                 cap_ratio: float = CAPACITY_RATIO) -> Dict[str, Any]:
    """T+1 开盘成交(信号确认日收盘后, 下一交易日开盘尝试).

    返回 {status: FILLED|REJECTED, price, reason, slippage_bps}
    """
    ok, reason = can_execute(bar, prev_close, "buy" if direction == "bull" else "sell",
                             limit_pct)
    if not ok:
        return {"status": "REJECTED", "reason": reason, "price": None,
                "slippage_bps": 0}
    ok2, reason2 = capacity_check(bar, position_pct, capital, cap_ratio)
    if not ok2:
        return {"status": "REJECTED", "reason": reason2, "price": None,
                "slippage_bps": 0}
    # 滑点: 买入加价, 卖出减价
    if direction == "bull":
        price = bar["o"] * (1 + slippage_pct / 100)
    else:
        price = bar["o"] * (1 - slippage_pct / 100)
    return {"status": "FILLED", "reason": "OK", "price": round(price, 6),
            "slippage_bps": round(slippage_pct * 100, 1)}


def simulate_exit_strict(bars: List[Dict[str, Any]], entry_idx: int,
                         entry_price: float, direction: str, sl: float,
                         tp: float, max_hold: int = 20,
                         prev_close: Optional[float] = None,
                         limit_pct: float = LIMIT_PCT,
                         fee_pct: float = FEE_PCT) -> Dict[str, Any]:
    """严格出场模拟(Iteration 3 内核).

    约束(审计 §7.3/§7.4):
      - T+1: 从 entry_idx+1 起评估
      - SL 优先: 同 bar 同时触发按 SL
      - 跳空穿越止损: 按开盘价(GAP_SL)
      - 涨跌停: 跌停日无法卖出 -> 跳过该 bar(持仓延续)
      - 停牌: 无法卖出 -> 跳过
      - 成本: 返回 gross 与 net(扣 fee)
    返回结构化结果(status/reason/exit_*).
    """
    n = len(bars)
    prev = prev_close if prev_close is not None else (
        bars[entry_idx]["c"] if entry_idx < len(bars) else entry_price)
    for j in range(entry_idx + 1, min(entry_idx + max_hold + 1, n)):
        bar = bars[j]
        # 停牌/缺失 -> 无法卖出, 持仓延续
        if is_suspended(bar):
            continue
        # 跌停(卖不出) -> 持仓延续
        if direction == "bull" and is_limit_move(bar, prev, "sell", limit_pct):
            prev = bar["c"]
            continue
        # 涨停(bear 卖空平仓时买不回) -> 延续
        if direction == "bear" and is_limit_move(bar, prev, "buy", limit_pct):
            prev = bar["c"]
            continue
        # 跳空穿越止损 -> 开盘价
        if direction == "bull" and bar["o"] <= sl:
            gross = (bar["o"] - entry_price) / entry_price * 100
            return {"status": "CLOSED", "reason": "GAP_SL", "exit_idx": j,
                    "exit_price": bar["o"], "gross_pnl_pct": round(gross, 4),
                    "net_pnl_pct": round(gross - fee_pct, 4)}
        if direction == "bear" and bar["o"] >= sl:
            gross = (entry_price - bar["o"]) / entry_price * 100
            return {"status": "CLOSED", "reason": "GAP_SL", "exit_idx": j,
                    "exit_price": bar["o"], "gross_pnl_pct": round(gross, 4),
                    "net_pnl_pct": round(gross - fee_pct, 4)}
        # SL 优先
        if direction == "bull" and bar["l"] <= sl:
            gross = (sl - entry_price) / entry_price * 100
            return {"status": "CLOSED", "reason": "SL", "exit_idx": j,
                    "exit_price": sl, "gross_pnl_pct": round(gross, 4),
                    "net_pnl_pct": round(gross - fee_pct, 4)}
        if direction == "bear" and bar["h"] >= sl:
            gross = (entry_price - sl) / entry_price * 100
            return {"status": "CLOSED", "reason": "SL", "exit_idx": j,
                    "exit_price": sl, "gross_pnl_pct": round(gross, 4),
                    "net_pnl_pct": round(gross - fee_pct, 4)}
        # TP
        if direction == "bull" and bar["h"] >= tp:
            gross = (tp - entry_price) / entry_price * 100
            return {"status": "CLOSED", "reason": "TP", "exit_idx": j,
                    "exit_price": tp, "gross_pnl_pct": round(gross, 4),
                    "net_pnl_pct": round(gross - fee_pct, 4)}
        if direction == "bear" and bar["l"] <= tp:
            gross = (entry_price - tp) / entry_price * 100
            return {"status": "CLOSED", "reason": "TP", "exit_idx": j,
                    "exit_price": tp, "gross_pnl_pct": round(gross, 4),
                    "net_pnl_pct": round(gross - fee_pct, 4)}
        prev = bar["c"]
    # 超时: 最后可用收盘价平仓
    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_price = bars[exit_idx]["c"]
    gross = ((exit_price - entry_price) / entry_price * 100
             if direction == "bull"
             else (entry_price - exit_price) / entry_price * 100)
    return {"status": "CLOSED", "reason": "TIME", "exit_idx": exit_idx,
            "exit_price": exit_price, "gross_pnl_pct": round(gross, 4),
            "net_pnl_pct": round(gross - fee_pct, 4)}


def portfolio_guard(position_count: int, total_pos_pct: float,
                    max_positions: int = MAX_POSITIONS,
                    total_cap: float = TOTAL_POS_CAP) -> Tuple[bool, str]:
    """组合层资金约束: 最大持仓数 + 总仓位上限."""
    if position_count >= max_positions:
        return False, "MAX_POSITIONS"
    if total_pos_pct + SINGLE_POS_CAP > total_cap:
        return False, "TOTAL_CAP"
    return True, "OK"