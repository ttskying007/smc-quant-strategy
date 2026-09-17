# -*- coding: utf-8 -*-
"""strategy_contract.py —— 单一策略合同工具(审计 §5.2 / Iteration 6).

审计 §5.2: 每个策略版本必须携带一份机器可校验的合同, 扫描器/回测器/执行器
和前端都从同一合同读取, 而不是各自解释字符串版本名。
Iteration 6 验收: 生产 registry、scanner、execution、frontend 四者的
contract hash 一致。

本模块:
  - build_contract(strategy_id, ...): 构造机器可校验合同
  - contract_hash(contract): 稳定哈希(SHA256)
  - verify_contract(contract, expected_hash): 校验合同未被篡改
  - signature(): 合同签名(供四端一致性校验)
纯内存, 不写生产.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


def build_contract(strategy_id: str,
                   data_contract: Optional[Dict[str, Any]] = None,
                   decision_delay: str = "T+1_OPEN",
                   cost_model: Optional[Dict[str, float]] = None,
                   target_visibility: str = "PRE_ENTRY_CONFIRMED_ONLY",
                   parameter_policy: str = "ROLLING_PAST_ONLY",
                   research_gate: Optional[Dict[str, int]] = None,
                   production_write: bool = False,
                   signal_contract: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造单一策略合同(审计 §5.2 示例字段)."""
    contract = {
        "strategy_id": strategy_id,
        "signal_contract": signal_contract or {
            "ontology": "PURE_SMC_SSL_RECLAIM",
            "template": "confirmed_SSL->sweep/reclaim->response_break->T+1_open",
            "outcome_blind": True,
        },
        "data_contract": data_contract or {
            "timeframe": "1d",
            "source": "kline_cache",
            "adjustment": "qfq",
        },
        "decision_delay": decision_delay,
        "cost_model": cost_model or {"round_trip_pct": 0.20},
        "target_visibility": target_visibility,
        "parameter_policy": parameter_policy,
        "research_gate": research_gate or {
            "min_n": 1000, "min_year_n": 300,
            "wr_min": 55.0, "pf_min": 1.15, "payoff_min": 0.70,
        },
        "production_write": production_write,
    }
    return contract


def contract_hash(contract: Dict[str, Any]) -> str:
    """稳定哈希: 规范化 JSON 后 SHA256 前 16 位."""
    canonical = json.dumps(contract, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def verify_contract(contract: Dict[str, Any], expected_hash: str) -> tuple[bool, str]:
    """校验合同未被篡改."""
    actual = contract_hash(contract)
    if actual != expected_hash:
        return False, "HASH_MISMATCH: %s != %s" % (actual, expected_hash)
    return True, "OK"


def signature(contract: Dict[str, Any]) -> Dict[str, Any]:
    """合同签名: 含 hash + 关键字段摘要, 供四端一致性校验."""
    h = contract_hash(contract)
    return {
        "strategy_id": contract["strategy_id"],
        "contract_hash": h,
        "decision_delay": contract["decision_delay"],
        "target_visibility": contract["target_visibility"],
        "production_write": contract["production_write"],
        "gate": contract["research_gate"],
    }


def four_end_consistent(registry: Dict[str, Any],
                        scanner_sig: Dict[str, Any],
                        execution_sig: Dict[str, Any],
                        frontend_sig: Dict[str, Any]) -> tuple[bool, Dict[str, str]]:
    """Iteration 6 验收: 生产 registry / scanner / execution / frontend
    四者 contract hash 一致.

    registry 携带 production_strategy + contract_hash(期望);
    scanner/execution/frontend 各自携带 contract_hash(实际).
    """
    expected = registry.get("contract_hash")
    if expected is None:
        return False, {"reason": "REGISTRY_NO_CONTRACT_HASH"}
    parts = {"registry": expected,
             "scanner": scanner_sig.get("contract_hash"),
             "execution": execution_sig.get("contract_hash"),
             "frontend": frontend_sig.get("contract_hash")}
    ok = all(v == expected for v in parts.values() if v is not None)
    return ok, parts