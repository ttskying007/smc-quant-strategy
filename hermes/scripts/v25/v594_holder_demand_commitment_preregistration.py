#!/usr/bin/env python3
"""Freeze V594 before any price response or outcome is read."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
LATEST = AUDIT / 'v594_holder_demand_commitment_preregistration_latest.json'
OUT = AUDIT / f'v594_holder_demand_commitment_preregistration_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V594_HOLDER_DEMAND_COMMITMENT_PREREGISTRATION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'purpose': 'Test a distinct PIT voluntary-holder-demand ontology: a disclosed controlling-holder, major-holder, director, or senior-management increase plan/first increase precedes a confirmed external BSL break and retest of the resulting demand OB. It is not a shareholder-snapshot feature, buyback, earnings, reduction, lockup, or price-only branch.',
        'source_contract': {
            'metadata': '/root/.hermes/smc_audit/v563_pit_event_archive_full_coverage_no_outcome_20260724_124935/v563_event_metadata.jsonl',
            'allowed_metadata_fields': ['symbol', 'announcement_id', 'kind', 'notice_date', 'publication_time', 'title'],
            'event_rule': 'kind=HOLDER_INCREASE; title contains 增持计划 or 增持公司股份 or 增持股份; excludes progress/completion/result/termination/adjustment/correction/over-half/expiry/legal-opinion/implementation-status notices. One earliest eligible disclosure per symbol and notice date.',
            'price_source': '/root/.hermes/kline_cache/*_daily_750.json with OHLC only through planned entry',
            'years': ['2023', '2024', '2025'], 'same_day_execution_forbidden': True,
        },
        'causal_contract': {
            'sequence': 'PIT_HOLDER_DEMAND_COMMITMENT -> later confirmed external BSL break by close within 30 sessions -> last bearish displacement candle demand OB -> first retest and close reclaim within 15 sessions -> next-session open entry',
            'information_timing': 'A 3L/3R pivot may be used only after right confirmation and before the break. The event itself cannot be a response or entry session. The OB is fixed before its retest. All nodes must precede entry.',
            'poi': 'last bearish candle between the event and close above a known external BSL, bounded by candle low/open; not an FVG or SSL/opening-range proxy.',
            'poisoned_families_excluded': ['PIT shareholder snapshot features', 'BUYBACK commitment demand retest', 'earnings attention volume-FVG', 'holder reduction SSL exhaustion', 'lockup supply exhaustion', 'pure price-only local structure'],
        },
        'support_gate': {'canonical_seed_total_min': 1000, 'canonical_seed_each_year_min': 300, 'unique_symbols_min': 500},
        'frozen_execution_if_authorized': {'entry': 'first daily open after reclaim', 'stop': 'demand OB low * 0.99', 'target': 'nearest unconsumed pre-entry right-confirmed daily swing high with planned RR >= 1.5', 'exits': 'strict T+1 only; gap-aware conservative stop-first collision; time20; fee 0.20%; serial position per symbol'},
        'strategy_quality_gate': {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'every_year_avg_net_positive': True, 't1_violations': 0},
        'no_variant_rule': 'Support failure closes without outcomes. Oracle mismatch closes without replay. A frozen strict-T+1 quality failure closes this ontology without selector, timing, stop, target, hold, calendar, or symbol variants.',
        'decision': 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v594_preregistration.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
