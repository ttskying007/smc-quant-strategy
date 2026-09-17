# -*- coding: utf-8 -*-
"""replay_chain.py —— 端到端经济回放编排器(审计 §5.1/§5.3 / Iteration 3).

审计 §5.1 分层结构: DataSnapshot -> BarStream -> CausalEventEngine ->
DecisionPolicy -> ExecutionSimulator -> Ledger -> ResearchGate/ProductionScanner.
审计 §5.3 属性测试: 在线逐bar与批量回放一致; 追加未来bar不改变历史.

本模块把已建成的组件串成**完整回放链**(纯内存, 合成数据可验证):
  - CausalEventEngine(事件流) -> 事件
  - DecisionPolicy: 事件 -> 候选(含 SL/TP, 仅入场前可见结构)
  - ExecutionSimulator: 次日开盘成交(涨跌停/停牌/容量/成本)
  - PortfolioSimulator: 组合资金(重叠/持仓数/资金占用)
  - Ledger: 每笔交易记录 + 数据 epoch
  - strategy_contract: 合同校验(生产写入=False)

核心性质(§5.3):
  * 在线逐bar == 批量回放(事件 ID 一致)
  * 追加未来 bar 不改变历史决策
  * 拒绝原因全程记录(不静默成交)
纯内存, 不写生产.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from causal_stream import CausalEventEngine
from execution_simulator import simulate_exit_strict, FEE_PCT
from portfolio_simulator import PortfolioSimulator
from strategy_contract import build_contract, contract_hash


class DecisionPolicy:
    """只读 visible_at <= now 的事件, 生成候选(审计 §5.1).

    候选含: symbol/entry_price(次日开盘)/sl(结构失败位)/tp(入场前可见目标).
    演示实现: 用固定 R 倍数目标与 ATR 止损(可被真实结构替换).
    """

    def __init__(self, tp_mult: float = 2.0, sl_atr: float = 1.5) -> None:
        self.tp_mult = tp_mult
        self.sl_atr = sl_atr

    def decide(self, events: set, bars_by_symbol: Dict[str, List[Dict[str, Any]]],
               sweep_by_symbol: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """事件 -> 候选: 计算次日开盘入场价、ATR 止损、2R 目标."""
        def _dk(x: str) -> str:
            return "".join(c for c in str(x) if c.isdigit())[:8]

        cands = []
        for sym, swing_date, sweep_date, response_date in events:
            bars = bars_by_symbol.get(sym, [])
            # 定位 response 之后的下一根 bar(entry_eligible)
            idx = None
            for i, b in enumerate(bars):
                if _dk(b.get("t", "")) == _dk(response_date):
                    idx = i
                    break
            if idx is None or idx + 1 >= len(bars):
                continue
            entry_bar = bars[idx + 1]
            entry_price = entry_bar["o"]
            if entry_price <= 0:
                continue
            # ATR 止损(过去 14 根, 无未来)
            atr = 0.0
            if idx >= 15:
                trs = []
                for k in range(idx - 14, idx):
                    trs.append(max(bars[k]["h"] - bars[k]["l"],
                                   abs(bars[k]["h"] - bars[k - 1]["c"]),
                                   abs(bars[k]["l"] - bars[k - 1]["c"])))
                atr = sum(trs) / len(trs) if trs else 0
            sl = entry_price - max(0.01, self.sl_atr * atr) if atr > 0 else entry_price * 0.95
            tp = entry_price * (1 + self.tp_mult * (entry_price - sl) / entry_price)
            cands.append({"symbol": sym, "entry_date": entry_bar["t"],
                          "entry_price": round(entry_price, 6),
                          "sl": round(sl, 6), "tp": round(tp, 6),
                          "direction": "bull"})
        return cands


class ReplayChain:
    """端到端回放链: 事件流 -> 决策 -> 成交 -> 组合 -> 台账."""

    def __init__(self, capital: float = 1_000_000.0,
                 max_positions: int = 10) -> None:
        self.engine = CausalEventEngine()
        self.policy = DecisionPolicy()
        self.portfolio = PortfolioSimulator(capital=capital,
                                            max_positions=max_positions)
        self.contract = build_contract("SMC_SSL_RECLAIM_V1")
        self.contract_hash = contract_hash(self.contract)
        self.ledger: List[Dict[str, Any]] = []
        self.rejects: List[Dict[str, Any]] = []

    def run(self, bars_by_symbol: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """逐 symbol 推进事件流, 再按日期推进组合(简化: 单 symbol 单次)."""
        all_events = {}
        for sym, bars in bars_by_symbol.items():
            eng = CausalEventEngine(sym)
            for b in bars:
                eng.step(b)
            all_events[sym] = eng.event_ids()
        # 决策 + 成交 + 组合
        for sym, events in all_events.items():
            bars = bars_by_symbol.get(sym, [])
            cands = self.policy.decide(events, {sym: bars}, {})
            for c in cands:
                r = self.portfolio.try_buy(sym, c["entry_date"], bars[0],
                                           c["entry_price"], c["sl"], c["tp"],
                                           bars=bars,
                                           prev_close=bars[0]["c"])
                if r["status"] != "FILLED":
                    self.rejects.append(r)
                    continue
                self.ledger.append({**c, "fill": r["price"]})
        return {"contract_hash": self.contract_hash,
                "trades": self.ledger, "rejects": self.rejects,
                "n_events": sum(len(v) for v in all_events.values())}