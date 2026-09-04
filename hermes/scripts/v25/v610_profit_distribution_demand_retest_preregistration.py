#!/usr/bin/env python3
"""V610: immutable ontology contract before reading any profit-distribution price response."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

AUDIT = Path('/root/.hermes/smc_audit')
CATALOG = AUDIT / 'v609_cash_dividend_plan_event_catalog_latest.json'
LATEST = AUDIT / 'v610_profit_distribution_demand_retest_preregistration_latest.json'
OUT = AUDIT / f'v610_profit_distribution_demand_retest_preregistration_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'


def main() -> None:
    catalog = json.loads(CATALOG.read_text())
    if catalog['decision'] != 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT':
        raise RuntimeError('V609 complete source catalog required')
    if not catalog['coverage']['all_days_complete']:
        raise RuntimeError('V609 full calendar coverage required')
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V610_PROFIT_DISTRIBUTION_DEMAND_RETEST_PREREGISTRATION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'purpose': 'Test a distinct PIT shareholder-distribution ontology: a newly disclosed annual profit-distribution plan precedes acceptance above a confirmed external BSL and a first demand-OB retest/reclaim. This is not an equity-incentive, buyback, holder, earnings, lending, lockup, contract-award, margin, or price-only ontology.',
        'source_contract': {
            'catalog': str(CATALOG),
            'events': catalog['artifacts']['events'],
            'allowed_event_fields': ['symbol', 'announcement_id', 'notice_date', 'publication_time', 'title', 'matched_terms'],
            'event_rule': 'One earliest eligible annual profit-distribution-plan announcement per A-share symbol and notice date: title contains 利润分配预案, 现金分红预案, or 利润分配方案; excludes 实施, 权益分派, 除权除息, 调整, 更正, 终止, 进展, 结果, 完成, 法律意见书, 独立财务顾问, 征求投资者意见, and 转增股本. Same-day response and execution are forbidden.',
            'price_source': '/root/.hermes/kline_cache/*_daily_750.json, OHLC only through each planned entry',
            'years': ['2023', '2024', '2025'],
        },
        'causal_contract': {
            'sequence': 'PIT_PROFIT_DISTRIBUTION_PLAN -> later close above a 3L/3R-confirmed external BSL within 30 sessions -> last bearish candle after event and before break defines demand OB -> first later retest with close reclaim within 15 sessions -> next-session open entry',
            'information_timing': 'The disclosure day is never a response or entry day. A BSL pivot is usable only after right-side confirmation and before its break. The OB is fixed before retest. Every causal node must precede entry.',
            'poi': 'Last bearish daily candle between the PIT distribution-plan event and BSL-acceptance close, bounded by candle low/open. No FVG, SSL, opening-range, volume, outcome, or future feature is permitted.',
        },
        'support_gate': {'canonical_seed_total_min': 1000, 'canonical_seed_each_year_min': 300, 'unique_symbols_min': 500},
        'frozen_execution_if_authorized': {
            'entry': 'first daily open after reclaim',
            'stop': 'demand OB low * 0.99',
            'target': 'nearest unconsumed pre-entry right-confirmed daily swing high with planned RR >= 1.5',
            'exits': 'strict T+1 only; gap-aware conservative stop-first collision; time20; fee 0.20%; serial position per symbol',
        },
        'strategy_quality_gate': {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'every_year_avg_net_positive': True, 't1_violations': 0},
        'no_variant_rule': 'Support failure closes without outcomes. Oracle mismatch closes without replay. One frozen strict-T+1 quality failure closes this ontology without selector, timing, stop, target, hold, calendar, or symbol variants.',
        'decision': 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v610_preregistration.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
