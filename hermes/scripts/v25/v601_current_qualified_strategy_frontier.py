#!/usr/bin/env python3
"""No-write reconciliation after the V598 contract-award ontology replay."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

AUDIT = Path('/root/.hermes/smc_audit')
OUT = AUDIT / 'v601_current_qualified_strategy_frontier_latest.json'


def load(name: str) -> dict:
    return json.loads((AUDIT / name).read_text())


def main() -> None:
    v582 = load('v582_lockup_release_ssl_exhaustion_seed_latest.json')
    v587 = load('v587_v585_frozen_strict_t1_replay_latest.json')
    v590 = load('v590_buyback_commitment_demand_retest_seed_latest.json')
    v592 = load('v592_earnings_attention_volume_fvg_seed_latest.json')
    v595 = load('v595_holder_demand_commitment_seed_latest.json')
    v598 = load('v598_contract_award_demand_retest_seed_latest.json')
    v599 = load('v599_v598_independent_raw_oracle_latest.json')
    v600 = load('v600_v598_frozen_strict_t1_replay_latest.json')

    assert v582['decision'].endswith('CLOSE_OBJECT')
    assert v587['decision'] == 'V587_FROZEN_REPLAY_GATE_FAIL__CLOSE_V585_ONTOLOGY_NO_VARIANTS'
    assert v590['decision'].endswith('CLOSE_ONTOLOGY')
    assert v592['decision'].endswith('CLOSE_ONTOLOGY')
    assert v595['decision'].endswith('CLOSE_ONTOLOGY')
    assert v598['decision'] == 'V598_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED'
    assert v599['identity_match'] is True
    assert v600['decision'] == 'V600_FROZEN_REPLAY_GATE_FAIL__CLOSE_V598_ONTOLOGY_NO_VARIANTS'
    assert v600['invariants']['t1_violations'] == 0

    quality_gate = v600['promotion_gate']
    report = {
        'version': 'V601_CURRENT_QUALIFIED_STRATEGY_FRONTIER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'fixed_strategy_gate': quality_gate,
        'completed_new_pit_event_ontologies': {
            'lockup_supply_absorption': {
                'seeds': v582['canonical_seed_count'],
                'years': v582['canonical_seed_years'],
                'decision': v582['decision'],
                'replay_opened': False,
            },
            'insider_reduction_exhaustion': {
                'closed_trades': v587['closed_trade_count'],
                'overall': v587['overall'],
                'decision': v587['decision'],
            },
            'buyback_commitment_demand': {
                'seeds': v590['canonical_seed_count'],
                'years': v590['canonical_seed_years'],
                'decision': v590['decision'],
                'replay_opened': False,
            },
            'earnings_attention_volume_fvg': {
                'seeds': v592['canonical_seed_count'],
                'years': v592['canonical_seed_years'],
                'decision': v592['decision'],
                'replay_opened': False,
            },
            'holder_demand_commitment': {
                'seeds': v595['canonical_seed_count'],
                'years': v595['canonical_seed_years'],
                'decision': v595['decision'],
                'replay_opened': False,
            },
            'contract_award_demand_retest': {
                'seeds': v598['canonical_seed_count'],
                'years': v598['canonical_seed_years'],
                'oracle_identity_match': v599['identity_match'],
                'closed_trades': v600['closed_trade_count'],
                'overall': v600['overall'],
                'yearly': v600['yearly'],
                'promotion_checks': v600['promotion_checks'],
                't1_violations': v600['invariants']['t1_violations'],
                'decision': v600['decision'],
            },
        },
        'invariants': {
            'all_artifacts_research_only': True,
            'no_production_or_frontend_or_watchlist_write': True,
            'only_one_frozen_replay_for_v598': v600['invariants']['search_count'] == 1,
            'v598_oracle_exact_identity_match': v599['identity_match'],
            'v598_strict_t1_violations_zero': v600['invariants']['t1_violations'] == 0,
            'no_closed_ontology_variant_authorized': True,
        },
        'decision': 'NO_QUALIFIED_STRATEGY_UNDER_CURRENT_AVAILABLE_PIT_AND_OHLCV__EMPTY_BOOK_REMAINS__NEW_INDEPENDENT_PIT_SOURCE_REQUIRED',
        'only_reopen_condition': (
            'A date-sensitive, publication-time-verified PIT causal state outside the six completed event families, '
            'with sufficient complete annual outcome-blind support before a single frozen replay. '
            'Threshold, timing, stop, target, hold, calendar, symbol, or timeframe variants of closed ontologies remain prohibited.'
        ),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
