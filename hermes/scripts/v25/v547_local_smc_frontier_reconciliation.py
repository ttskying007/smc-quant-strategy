#!/usr/bin/env python3
"""No-write reconciliation of the current local m15/volume research frontier."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

A = Path('/root/.hermes/smc_audit')
OUT = A / 'v547_local_smc_frontier_reconciliation_latest.json'
inputs = {
    'sina_coverage': A/'v536_sina_partial_coverage_latest.json',
    'tick_gate': A/'v407_pit_tick_history_availability_latest.json',
    'price_seed': A/'v539_sina_m15_ssl_bos_fvg_seed_gate_latest.json',
    'price_oracle': A/'v540_sina_m15_ssl_bos_fvg_independent_oracle_latest.json',
    'price_replay': A/'v541_sina_m15_ssl_bos_fvg_frozen_t1_replay_latest.json',
    'volume_seed': A/'v543_sina_m15_ssl_displacement_absorption_seed_gate_latest.json',
    'volume_oracle': A/'v544_sina_m15_ssl_displacement_absorption_independent_oracle_latest.json',
    'volume_replay': A/'v545_sina_m15_ssl_displacement_absorption_frozen_t1_replay_latest.json',
    'volume_attribution': A/'v546_sina_m15_v545_failure_attribution_latest.json',
}

def load(key: str) -> dict:
    return json.loads(inputs[key].read_text())

def main() -> None:
    data = {key: load(key) for key in inputs}
    assert data['price_oracle']['identity_match'] and data['volume_oracle']['identity_match']
    assert data['price_replay']['invariants']['t1_violations'] == 0 and data['volume_replay']['invariants']['t1_violations'] == 0
    result = {
      'version': 'V547_LOCAL_SMC_FRONTIER_RECONCILIATION_NO_WRITE',
      'generated_at': datetime.now().isoformat(timespec='seconds'),
      'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
      'usable_definition': {'required': ['same-source complete canonical full-history universe', 'outcome-blind seed support', 'independent identity oracle equality', 'one frozen strict-T+1 replay', 'n>=1000 and each year>=300', 'WR>=55%', 'avg net>=0.50%', 'PF>=1.15', 'payoff>=0.70', 'each year average net>0', 'T+1 violations=0'], 'meaning': 'Only all-pass may enter a separate scanner-time/production authorization stage.'},
      'unusable_definition': 'Any missing source-contract requirement, oracle mismatch, frozen replay failure, or post-outcome bucket is not a strategy and cannot be promoted.',
      'completed': {
        'price_only_ssl_bos_fvg': {'seed': data['price_seed']['seed_count'], 'oracle_identity_match': data['price_oracle']['identity_match'], 'replay': data['price_replay']['overall'], 'decision': data['price_replay']['decision']},
        'volume_displacement_absorption': {'seed': data['volume_seed']['seed_count'], 'oracle_identity_match': data['volume_oracle']['identity_match'], 'replay': data['volume_replay']['overall'], 'yearly': data['volume_replay']['yearly'], 'attribution_mechanics': data['volume_attribution']['mechanics'], 'decision': data['volume_replay']['decision']},
      },
      'data_frontier': {'sina_m15': data['sina_coverage']['full_market_2023_2026_research'], 'sina_promotion': data['sina_coverage']['promotion'], 'historical_tick': data['tick_gate']['decision']},
      'unfinished_but_blocked': ['Full-history same-source canonical-universe intraday research is blocked: Sina m15 begins 2025 and Baostock raw MTF cache is an audited subset, not the full canonical universe.', 'Auction/order-flow/tick ontology is blocked: historical tick responses are not date-sensitive.'],
      'prohibited_next_steps': ['No threshold/window/SL/TP/hold/time-bucket/year-bucket variants of V539/V541 or V543/V545.', 'No production, scanner, watchlist, frontend, or historical-trade fallback routing.'],
      'reopen_condition': 'A genuinely new PIT causal data dimension with date-sensitive full-history same-source canonical-universe coverage, followed by a new preregistered seed/oracle/frozen-replay chain.',
      'decision': 'CURRENT_LOCAL_OHLCV_PLUS_VOLUME_FRONTIER_COMPLETE__ZERO_PROMOTION_PASS__EMPTY_BOOK_REMAINS',
      'inputs': {key: str(path) for key, path in inputs.items()},
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == '__main__': main()
