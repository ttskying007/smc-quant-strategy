#!/usr/bin/env python3
"""V616 immutable contract before reading any pledge-event price response."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

AUDIT = Path('/root/.hermes/smc_audit')
CATALOG = AUDIT / 'v615_controlling_pledge_pit_event_catalog_latest.json'
LATEST = AUDIT / 'v616_controlling_pledge_release_demand_retest_preregistration_latest.json'
OUT = AUDIT / f'v616_controlling_pledge_release_demand_retest_preregistration_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'


def main() -> None:
    catalog = json.loads(CATALOG.read_text())
    if catalog['decision'] != 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT':
        raise RuntimeError('V615 complete source catalog required')
    if not catalog['coverage']['all_days_complete']:
        raise RuntimeError('V615 complete calendar coverage required')
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V616_CONTROLLING_HOLDER_PLEDGE_RELEASE_DEMAND_RETEST_PREREGISTRATION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'purpose': 'Test a distinct PIT ownership-risk-release ontology: a timestamped controlling-holder pledge-release disclosure precedes acceptance above a confirmed external BSL and a first demand-OB retest/reclaim. Pledge creation is explicitly excluded because it is a different causal state, not a selector variant.',
        'source_contract': {
            'catalog': str(CATALOG), 'events': catalog['artifacts']['events'],
            'allowed_event_fields': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'event_kind', 'title'],
            'event_rule': 'One earliest controlling-holder pledge-release disclosure per A-share symbol and notice date, event_kind=CONTROLLING_HOLDER_PLEDGE_RELEASE. Same-day response and execution are forbidden.',
            'price_source': '/root/.hermes/kline_cache/*_daily_750.json, OHLC only through each planned entry',
            'years': ['2023', '2024', '2025'],
        },
        'causal_contract': {
            'sequence': 'PIT_CONTROLLING_HOLDER_PLEDGE_RELEASE -> later close above a 3L/3R-confirmed external BSL within 30 sessions -> last bearish candle after event and before break defines demand OB -> first later retest with close reclaim within 15 sessions -> next-session open entry',
            'information_timing': 'The disclosure day is never a response or entry day. A BSL pivot is usable only after right-side confirmation and before its break. The OB is fixed before retest. Every causal node must precede entry.',
            'poi': 'Last bearish daily candle between the pledge-release event and BSL-acceptance close, bounded by candle low/open. No FVG, SSL, opening-range, volume, outcome, or future feature is permitted.',
        },
        'support_gate': {'canonical_seed_total_min': 1000, 'canonical_seed_each_year_min': 300, 'unique_symbols_min': 500},
        'frozen_execution_if_authorized': {
            'entry': 'first daily open after reclaim', 'stop': 'demand OB low * 0.99',
            'target': 'nearest unconsumed pre-entry right-confirmed daily swing high with planned RR >= 1.5',
            'exits': 'strict T+1 only; gap-aware conservative stop-first collision; time20; fee 0.20%; serial position per symbol',
        },
        'strategy_quality_gate': {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'every_year_avg_net_positive': True, 't1_violations': 0},
        'no_variant_rule': 'Support failure closes without outcomes. Oracle mismatch closes without replay. One frozen strict-T+1 quality failure closes this ontology without selector, timing, stop, target, hold, calendar, or symbol variants.',
        'decision': 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v616_preregistration.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
