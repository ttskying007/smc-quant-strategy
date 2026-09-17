# -*- coding: utf-8 -*-
"""portfolio_simulator.py —— 组合级资金模拟器(审计 §7.4 / Iteration 3).

审计 §7.4: "单标的重叠持仓和资金占用" / "组合层最大持仓数、行业暴露和单票风险".

本模块把 execution_simulator 的成交/资金约束组合成**组合资金引擎**:
  - 按日期推进事件流, 管理持仓状态机
  - 资金占用: 每笔占用 = 市值; 总占用 <= TOTAL_POS_CAP
  - 单票上限: 单票市值 <= SINGLE_POS_CAP * capital
  - 最大持仓数: 并行持仓 <= MAX_POSITIONS
  - 重叠信号: 同 symbol 未平仓时新信号拒绝(不重复占用资金)
  - 卖出释放资金后允许新买入

纯内存; 由调用方逐日喂 (date, events, bars) 推进.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from execution_simulator import (SINGLE_POS_CAP, TOTAL_POS_CAP,
                                 MAX_POSITIONS, capacity_check,
                                 is_suspended, simulate_exit_strict)


class PortfolioSimulator:
    """组合资金引擎: 持仓状态机 + 资金占用 + 并发约束."""

    def __init__(self, capital: float = 1_000_000.0,
                 max_positions: int = MAX_POSITIONS,
                 single_cap: float = SINGLE_POS_CAP,
                 total_cap: float = TOTAL_POS_CAP) -> None:
        self.capital = capital
        self.max_positions = max_positions
        self.single_cap = single_cap
        self.total_cap = total_cap
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position
        self.trades: List[Dict[str, Any]] = []
        self.rejects: List[Dict[str, Any]] = []

    def equity(self) -> float:
        """总权益 = 现金 + 持仓市值(按最近收盘估计)."""
        cash = self.capital - sum(p["market_value"] for p in self.positions.values())
        return cash + sum(p["market_value"] for p in self.positions.values())

    def _used_capital(self) -> float:
        return sum(p["market_value"] for p in self.positions.values())

    def try_buy(self, symbol: str, date: str, bar: Dict[str, Any],
                entry_price: float, sl: float, tp: float,
                direction: str = "bull", bars: Optional[List[Dict[str, Any]]] = None,
                prev_close: Optional[float] = None,
                position_pct: float = 0.05) -> Dict[str, Any]:
        """尝试买入(信号确认后下一交易日开盘).

        约束: 持仓数 / 单票上限 / 总占用 / 重叠信号 / 成交可执行性.
        """
        # 重叠信号: 同 symbol 未平仓 -> 拒绝
        if symbol in self.positions:
            self.rejects.append({"date": date, "symbol": symbol,
                                 "reason": "OVERLAP_POSITION"})
            return {"status": "REJECTED", "reason": "OVERLAP_POSITION"}

        n_pos = len(self.positions)
        if n_pos >= self.max_positions:
            self.rejects.append({"date": date, "symbol": symbol,
                                 "reason": "MAX_POSITIONS"})
            return {"status": "REJECTED", "reason": "MAX_POSITIONS"}

        order_amt = self.capital * position_pct
        # 总占用: 现有 + 本单 <= total_cap
        if self._used_capital() + order_amt > self.capital * self.total_cap:
            self.rejects.append({"date": date, "symbol": symbol,
                                 "reason": "TOTAL_CAP"})
            return {"status": "REJECTED", "reason": "TOTAL_CAP"}
        # 单票上限
        if order_amt > self.capital * self.single_cap:
            self.rejects.append({"date": date, "symbol": symbol,
                                 "reason": "SINGLE_CAP"})
            return {"status": "REJECTED", "reason": "SINGLE_CAP"}
        # 可执行性
        from execution_simulator import execute_open
        r = execute_open(bar, prev_close or entry_price, direction,
                         capital=self.capital, position_pct=position_pct)
        if r["status"] != "FILLED":
            self.rejects.append({"date": date, "symbol": symbol,
                                 "reason": r["reason"]})
            return {"status": "REJECTED", "reason": r["reason"]}
        fill = r["price"]
        self.positions[symbol] = {
            "symbol": symbol, "entry_date": date, "entry_price": fill,
            "sl": sl, "tp": tp, "direction": direction,
            "market_value": order_amt, "position_pct": position_pct,
            "bars": bars or [],
        }
        return {"status": "FILLED", "price": fill, "symbol": symbol,
                "entry_date": date}

    def try_exit(self, symbol: str, date: str, bar: Dict[str, Any],
                 prev_close: Optional[float] = None,
                 max_hold: int = 20) -> Dict[str, Any]:
        """尝试平仓(逐日调用): 用严格出场模拟."""
        pos = self.positions.get(symbol)
        if pos is None:
            return {"status": "NO_POSITION"}
        r = simulate_exit_strict(
            pos["bars"], 0, pos["entry_price"], pos["direction"],
            pos["sl"], pos["tp"], max_hold=max_hold,
            prev_close=prev_close)
        if r["status"] == "CLOSED":
            del self.positions[symbol]
            self.trades.append({**pos, "exit_date": date,
                                "exit_price": r["exit_price"],
                                "reason": r["reason"],
                                "net_pnl_pct": r["net_pnl_pct"]})
            return {"status": "CLOSED", **r}
        return {"status": "OPEN", **r}

    def day_step(self, date: str, events: List[Dict[str, Any]],
                 bars_by_symbol: Dict[str, List[Dict[str, Any]]],
                 prev_close_by_symbol: Optional[Dict[str, float]] = None) -> None:
        """单日推进: 先平仓(释放资金), 再尝试新买入."""
        # 先处理既有持仓的出场(该日 bar)
        for sym in list(self.positions.keys()):
            bars = bars_by_symbol.get(sym, [])
            if bars:
                pc = (prev_close_by_symbol or {}).get(sym)
                self.try_exit(sym, date, bars[0], prev_close=pc)
        # 再尝试新信号买入
        for ev in events:
            sym = ev.get("symbol")
            bars = bars_by_symbol.get(sym, [])
            if not bars:
                self.rejects.append({"date": date, "symbol": sym,
                                     "reason": "NO_BARS"})
                continue
            self.try_buy(sym, date, bars[0], ev.get("entry_price", 0),
                         ev.get("sl", 0), ev.get("tp", 0),
                         bars=bars,
                         prev_close=(prev_close_by_symbol or {}).get(sym))