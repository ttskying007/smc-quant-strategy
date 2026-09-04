#!/usr/bin/env python3
"""V601 no-write reconciliation after V596->V600 contract-award ontology."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

AUDIT = Path('/root/.hermes/smc_audit')
OUT = AUDIT / 'v601_current_available_data_strategy_frontier_latest.json'


def load(name: str) -> dict:
    return json.loads((AUDIT / name).read_text())


def main() -> None:
    v560 = load('v560_v553_v559_reconciliation_and_branch_closure_latest.json')
    v568 = load('v568_v566_frozen_strict_t1_replay_latest.json')
    v571 = load('v571_v569_frozen_strict_t1_replay_latest.json')
    v579 = load('v579_v577_frozen_strict_t1_replay_latest.json')
    v587 = load('v587_v585_frozen_strict_t1_replay_latest.json')
    v590 = load('v590_buyback_commitment_demand_retest_seed_latest.json')
    v592 = load('v592_earnings_attention_volume_fvg_seed_latest.json')
    v595 = load('v595_holder_demand_commitment_seed_latest.json')
    v596 = load('v596_contract_award_event_catalog_latest.json')
    v598 = load('v598_contract_award_demand_retest_seed_latest.json')
    v599 = load('v599_v598_independent_raw_oracle_latest.json')
    v600 = load('v600_v598_frozen_strict_t1_replay_latest.json')
    assert v560['decision'] == 'V553_V559_BRANCH_COMPLETE__FROZEN_REPLAY_GATE_FAILED__NO_MORE_VARIANTS__SOURCE_QUALIFICATION_ONLY'
    assert v596['decision'] == 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT'
    assert v598['decision'] == 'V598_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED'
    assert v599['identity_match'] is True
    assert v600['decision'] == 'V600_FROZEN_REPLAY_GATE_FAIL__CLOSE_V598_ONTOLOGY_NO_VARIANTS'
    closed = {
        'same_source_intraday_and_daily_mtf': v560['decision'],
        'industry_activation_m60': v568['decision'],
        'official_margin_commitment': v571['decision'],
        'official_lending_short_pressure': v579['decision'],
        'insider_reduction_supply_exhaustion': v587['decision'],
        'buyback_commitment': v590['decision'],
        'earnings_attention_volume_fvg': v592['decision'],
        'holder_demand_commitment': v595['decision'],
        'contract_award_demand_retest': v600['decision'],
    }
    report = {
        'version': 'V601_CURRENT_AVAILABLE_DATA_STRATEGY_FRONTIER_RECONCILIATION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'quality_gate': {'n_min': 1000, 'each_year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'every_year_avg_net_positive': True, 't1_violations': 0},
        'newest_branch_evidence': {
            'ontology': 'PIT contract award -> confirmed BSL acceptance -> demand OB retest/reclaim -> next open',
            'source_catalog': {'events': v596['canonical_candidate_events'], 'years': v596['candidate_events_by_year'], 'coverage_complete': v596['coverage']['all_days_complete']},
            'outcome_blind_support': {'seeds': v598['canonical_seed_count'], 'years': v598['canonical_seed_years'], 'unique_symbols': v598['unique_symbols'], 'support_pass': all(v598['support_checks'].values())},
            'independent_oracle': {'identity_match': v599['identity_match'], 'expected': v599['expected_identities'], 'actual': v599['oracle_identities']},
            'single_frozen_t1_replay': {'n': v600['overall']['n'], 'wr_pct': v600['overall']['wr_pct'], 'avg_net_pct': v600['overall']['avg_net_pct'], 'profit_factor': v600['overall']['profit_factor'], 'payoff': v600['overall']['payoff'], 'yearly': v600['yearly'], 't1_violations': v600['invariants']['t1_violations'], 'checks': v600['promotion_checks']},
            'decision': v600['decision'],
        },
        'closed_current_data_branches': closed,
        'conclusion': 'NO_STRATEGY_MEETS_THE_FIXED_QUALITY_GATE_FROM_CURRENT_AVAILABLE_LOCAL_OHLCV_OR_QUALIFIED_PIT_DATA. EMPTY_BOOK remains mandatory. Contract-award supply was sufficient and causally verified, but the single frozen replay failed economics; its ontology is closed without variants.',
        'legal_next_step': 'Only a genuinely new, date-addressable PIT information dimension or a new full-history canonical intraday source may start a new preregistered ontology. Reusing any closed event family, adding filters, changing timing, stop, target, hold, year, symbol subset, or time-frame is prohibited.',
        'decision': 'CURRENT_AVAILABLE_DATA_STRATEGY_FRONTIER_EXHAUSTED__NO_PRODUCTION_STRATEGY__EMPTY_BOOK__SOURCE_QUALIFICATION_ONLY',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
