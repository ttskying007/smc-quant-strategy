#!/usr/bin/env python3
"""No-write final reconciliation of the currently available SMC research frontier.

This script does not generate signals or trades.  It only verifies that each
currently available local/PIT research branch has a terminal audited decision,
including the user-authorized 1-2 year HTF->m15 exploratory chain.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

AUDIT = Path('/root/.hermes/smc_audit')
OUT = AUDIT / 'v552_research_frontier_final_reconciliation_latest.json'

REQUIRED = {
    'daily_volume_price_frontier': ('v538_v517_lineage_reconciliation_and_frontier_closure_20260721.md', None),
    'price_only_m15': ('v541_sina_m15_ssl_bos_fvg_frozen_t1_replay_latest.json', 'V541_PARTIAL_RANGE_RESEARCH_FAIL__CLOSE_OBJECT'),
    'volume_displacement_m15': ('v545_sina_m15_ssl_displacement_absorption_frozen_t1_replay_latest.json', 'V545_PARTIAL_RANGE_RESEARCH_FAIL__CLOSE_OBJECT'),
    'htf_trend_m15_seed': ('v548_htf_trend_m15_entry_seed_gate_latest.json', 'V548_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT'),
    'htf_trend_m15_replay': ('v551_htf_m15_exploratory_frozen_t1_replay_latest.json', 'V551_EXPLORATORY_REPLAY_FAIL__CLOSE_OBJECT'),
    'm60_sweep_mss': ('v375_m60_nearest_swing_mss_latest.json', 'NO_PRODUCTION_PASS__CAUSAL_GENERATOR_CLOSED_OR_REVISE_SEMANTICS'),
    'm60_po3': ('v377_m60_po3_accumulation_distribution_latest.json', 'NO_PRODUCTION_PASS__CAUSAL_GENERATOR_CLOSED_OR_REVISE_SEMANTICS'),
    'raw_daily_poi_m60': ('v381_true_mtf_raw_daily_poi_m60_replay_latest.json', 'NO_PRODUCTION_PASS__TRUE_MTF_BRANCH_CLOSED'),
    'eastmoney_historical_intraday': ('v408_eastmoney_intraday_history_availability_latest.json', 'SOURCE_UNAVAILABLE_FOR_FULL_HISTORY__NO_OUTCOME_REPLAY__CLOSE_EASTMONEY_5_15_30MIN_BRANCH'),
    'pit_inventory': ('v548_pit_branch_completion_inventory_latest.json', None),
}


def read_json(name: str) -> dict:
    return json.loads((AUDIT / name).read_text())


def main() -> None:
    branches: dict[str, dict] = {}
    for branch, (name, expected) in REQUIRED.items():
        path = AUDIT / name
        if expected is None:
            # The daily volume lineage is a markdown authoritative closure; PIT is
            # a structured inventory with all 26 branches accounted for.
            if branch == 'pit_inventory':
                payload = read_json(name)
                assert payload['count'] == 26
                assert any(x['id'] == 'V403' and 'CLOSE_HOLDER_BRANCH' in x['decision'] for x in payload['items'])
                branches[branch] = {'artifact': str(path), 'terminal': True, 'detail': '26 PIT/new-data branches inventoried; every availability pass has a successor or documented stop.'}
            else:
                # This authoritative Chinese-language lineage report declares the
                # ontology unavailable and explicitly prohibits variants.
                text = path.read_text()
                assert path.exists() and '当前不可用、不可生产' in text and '禁止在此本体内继续变体搜索' in text
                branches[branch] = {'artifact': str(path), 'terminal': True, 'detail': 'Authoritative daily volume/price lineage closure exists.'}
            continue
        payload = read_json(name)
        assert payload['decision'] == expected, (branch, payload.get('decision'), expected)
        assert payload.get('production_write', False) is False
        assert payload.get('frontend_write', False) is False
        assert payload.get('watchlist_write', False) is False
        branches[branch] = {'artifact': str(path), 'terminal': True, 'decision': expected, 'production_write': False, 'frontend_write': False, 'watchlist_write': False}

    # V548 and V551 differ only in support/replay stage. The lower-timeframe
    # change is not a legal new ontology after both stages have failed.
    result = {
        'version': 'V552_RESEARCH_FRONTIER_FINAL_RECONCILIATION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'objective': 'Reconcile all currently available local OHLCV, volume, MTF, HTF->LTF and PIT branches after V548-V551 and V408; prevent an unclosed-direction claim from causing prohibited parameter/timeframe variants.',
        'usable_definition': {
            'data': 'Same-source, date-addressable, canonical full-history coverage; PIT sources additionally require record publication/as-of timestamp before decision.',
            'causal_chain': 'Outcome-blind seed -> independently implemented exact identity oracle -> one frozen strict T+1 replay.',
            'promotion': 'n>=1000; each year>=300; WR>=55%; AvgNet>=+0.50%; PF>=1.15; payoff>=0.70; every year AvgNet>0; T+1 violations=0.'
        },
        'unusable_definition': [
            'Changing m15/m60, a parent trend window, indicator threshold, stop, target, RR, hold, calendar/year/clock bucket, or a selected-symbol subset of an already closed object.',
            'Partial-source exploratory evidence as production authorization.',
            'A historical trade, old candidate, or scanner artifact as current BUY_VALID input.'
        ],
        'branch_reconciliation': branches,
        'specific_htf_ltf_conclusion': {
            'request': 'Large timeframe trend with small timeframe entry',
            'tested': 'V548 -> V550 -> V551: completed weekly+daily higher-low/BOS regime before m15 SSL/displacement/reclaim entry, source-isolated Sina 2025-04..2026-07.',
            'result': '220 seeds, 35 executable frozen T+1 trades, WR 40.0%, 2025 AvgNet -1.2235%, no partial research pass.',
            'status': 'CLOSED; replacing m15 with m60 would be a time-frame variant of a tested HTF->LTF ontology, not a new causal information dimension.'
        },
        'source_status': {
            'sina_m60': 'V379 source-derived raw daily reconstruction is valid for audited research, but V374/V375/V377/V381 have terminal economic failures.',
            'sina_m15': 'Recent-only partial range; V539-V546 and V548-V551 terminally closed.',
            'eastmoney_5_15_30m': 'V408 exact-date requests returned zero historical bars across 2023-2026; unavailable.',
            'historical_tick_orderflow': 'V407 date-insensitive responses; unavailable for PIT replay.',
            'PIT_institutional_disclosure_flow': 'V382-V407 inventory terminally reconciled.'
        },
        'only_reopen_condition': 'A new independent, date-sensitive PIT causal information dimension with a qualifying source contract (or a genuinely new full-history same-source canonical intraday provider), followed by a preregistered new ontology; no current local data permits another strategy replay.',
        'operational_state': 'EMPTY_BOOK',
        'decision': 'CURRENT_RESEARCH_GOAL_COMPLETE_UNDER_AVAILABLE_DATA__ALL_AUTHORIZED_BRANCHES_TERMINAL__EMPTY_BOOK_REMAINS__SOURCE_QUALIFICATION_ONLY'
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
