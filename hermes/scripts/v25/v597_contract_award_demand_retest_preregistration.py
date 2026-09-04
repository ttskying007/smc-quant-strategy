#!/usr/bin/env python3
"""Freeze V597 before any price response or outcome is read."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
CATALOG = AUDIT / 'v596_contract_award_event_catalog_latest.json'
LATEST = AUDIT / 'v597_contract_award_demand_retest_preregistration_latest.json'
OUT = AUDIT / f'v597_contract_award_demand_retest_preregistration_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'


def main() -> None:
    catalog = json.loads(CATALOG.read_text())
    if catalog['decision'] != 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT':
        raise RuntimeError('V596 complete source catalog required')
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V597_CONTRACT_AWARD_DEMAND_RETEST_PREREGISTRATION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'purpose': 'Test a distinct PIT contract-award demand ontology: a public winning-bid or material-contract disclosure precedes acceptance above a confirmed external BSL and the first retest/reclaim of the resulting demand OB. This is not a buyback, holder plan, earnings, lending, lockup, reduction, or price-only ontology.',
        'source_contract': {
            'catalog': str(CATALOG),
            'events': catalog['artifacts']['events'],
            'allowed_event_fields': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'title', 'matched_terms'],
            'event_rule': 'One earliest catalogued event per symbol and notice date. The V596 catalog is immutable: title contains one of 中标, 重大合同, 签订合同, 签署合同, 合同金额, 获得订单, 收到订单.',
            'price_source': '/root/.hermes/kline_cache/*_daily_750.json, OHLC only through each planned entry',
            'years': ['2024', '2025'],
            'same_day_event_response_forbidden': True,
            'same_day_execution_forbidden': True,
        },
        'causal_contract': {
            'sequence': 'PIT_CONTRACT_AWARD -> on a later daily session within 30 sessions, close above a 3L/3R-confirmed external BSL -> last bearish candle after event and before break defines demand OB -> first later zone retest with close reclaim within 15 sessions -> next-session open entry',
            'information_timing': 'The disclosure day is never a response, reclaim, or entry day. A BSL pivot is usable only after right-side confirmation and before the break. The OB is fixed before retest. Every causal node must precede the planned entry.',
            'poi': 'Last bearish daily candle between the PIT event and BSL-acceptance close, bounded by candle low/open. No FVG, SSL, opening-range, volume, outcome, or future feature is permitted.',
            'poisoned_families_excluded': ['PIT_BUYBACK_COMMITMENT', 'PIT_HOLDER_DEMAND_COMMITMENT', 'PIT_EARNINGS_DISCLOSURE', 'PIT_LENDING_SELL_PRESSURE', 'PIT_INSIDER_REDUCTION_PLAN', 'PIT_LOCKUP_RELEASE', 'pure_price_only_local_structure'],
        },
        'support_gate': {
            'canonical_seed_total_min': 1000,
            'canonical_seed_each_available_year_min': 300,
            'unique_symbols_min': 500,
        },
        'frozen_execution_if_authorized': {
            'entry': 'first daily open after reclaim',
            'stop': 'demand OB low * 0.99',
            'target': 'nearest unconsumed pre-entry right-confirmed daily swing high with planned RR >= 1.5',
            'exits': 'strict T+1 only; gap-aware conservative stop-first collision; time20; fee 0.20%; serial position per symbol',
        },
        'strategy_quality_gate': {
            'n_min': 1000,
            'year_n_min': 300,
            'wr_pct_min': 55.0,
            'avg_net_pct_min': 0.50,
            'pf_min': 1.15,
            'payoff_min': 0.70,
            'every_year_avg_net_positive': True,
            't1_violations': 0,
        },
        'no_variant_rule': 'Support failure closes without outcomes. Oracle mismatch closes without replay. One frozen strict-T+1 quality failure closes this ontology without selector, timing, stop, target, hold, calendar, or symbol variants.',
        'decision': 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v597_preregistration.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
