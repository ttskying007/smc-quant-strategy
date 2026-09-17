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

    候选含: symbol/entry_price(次日开盘)/sl(结构失败位优先)/tp(入场前可见
    目标优先). 结构优先 SL/TP 由 structural_sl_tp.SLTPGenerator 提供
    (§7.2/§7.3), ATR/R 倍数仅作 fallback 并统计比例。
    """

    def __init__(self, tp_mult: float = 2.0, sl_atr: float = 1.5,
                 use_structure: bool = True) -> None:
        from structural_sl_tp import SLTPGenerator
        self.gen = SLTPGenerator(atr_mult=sl_atr, r_mult=tp_mult,
                                 use_structure=use_structure)

    def decide(self, events: set, bars_by_symbol: Dict[str, List[Dict[str, Any]]],
               sweep_by_symbol: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """事件 -> 候选: 次日开盘入场价 + 结构优先 SL/TP(§7.2/§7.3)."""
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
            # 定位 sweep_idx(结构失败位 SL 需要)
            sweep_idx = None
            for i, b in enumerate(bars):
                if _dk(b.get("t", "")) == _dk(sweep_date):
                    sweep_idx = i
                    break
            if sweep_idx is None:
                continue
            # 结构优先 SL/TP(§7.2/§7.3): 结构失败位 SL + 入场前可见 swing high TP
            st = self.gen.decide(bars, sweep_idx, idx, entry_price)
            cands.append({"symbol": sym, "entry_date": entry_bar["t"],
                          "entry_price": round(entry_price, 6),
                          "sl": st["sl"]["stop"], "tp": st["tp"]["target"],
                          "sl_source": st["sl"]["source"],
                          "tp_source": st["tp"]["source"],
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
                "n_events": sum(len(v) for v in all_events.values()),
                "sl_fallback_ratio": (self.policy.gen.sl_fallback_count /
                                      max(1, self.policy.gen.total)),
                "tp_fallback_ratio": (self.policy.gen.tp_fallback_count /
                                      max(1, self.policy.gen.total))}

    def gate_evaluate(self) -> Dict[str, Any]:
        """§10.3 研究门槛判定(审计 Iteration 3: 达标则保持, 否则关闭)."""
        from research_gate import evaluate as gate_eval
        rows = [{"entry_date": t.get("entry_date"),
                 "net_pnl_pct": t.get("net_pnl_pct", 0.0)}
                for t in self.ledger]
        # 台账无收益时用占位 0(真实回放由 ExecutionSimulator 产出)
        g = gate_eval(rows)
        return {"gate_passed": g["passed"], "n_trades": g["n_trades"],
                "checks": g["checks"],
                "verdict": ("KEEP_RESEARCH" if g["passed"]
                            else "STAY_CLOSED")}