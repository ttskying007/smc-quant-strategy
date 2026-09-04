#!/usr/bin/env python3
"""Freeze V589 before any price-response or outcome file is read."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
LATEST = AUDIT / 'v589_buyback_commitment_demand_retest_preregistration_latest.json'
OUT = AUDIT / f'v589_buyback_commitment_demand_retest_preregistration_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V589_BUYBACK_COMMITMENT_DEMAND_RETEST_PREREGISTRATION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'purpose': 'A distinct external-demand ontology: a public A-share buyback commitment precedes a bullish break of confirmed external BSL, then a retest/reclaim of the displacement demand OB. This is not an SSL-exhaustion or opening-range variant.',
        'source_contract': {
            'metadata': '/root/.hermes/smc_audit/v563_pit_event_archive_full_coverage_no_outcome_20260724_124935/v563_event_metadata.jsonl',
            'allowed_metadata_fields': ['symbol', 'announcement_id', 'kind', 'notice_date', 'publication_time', 'title'],
            'event_rule': 'kind=BUYBACK; title contains 回购 and one of 回购方案|回购股份方案|回购报告书|拟回购|回购预案|董事会; excludes 进展|实施|完成|结果|注销|调整|前十名|股份变动|账户|比例|价格上限|激励|补偿|减少注册资本|B股.',
            'event_identity': 'one earliest source document per symbol and notice date',
            'price_source': '/root/.hermes/kline_cache/*_daily_750.json',
            'years': ['2023', '2024', '2025'],
            'same_day_execution_forbidden': True,
        },
        'causal_contract': {
            'sequence': 'PIT_BUYBACK_COMMITMENT -> confirmed external BSL break by close within next 30 sessions -> last bearish displacement candle demand OB -> retest and close reclaim within next 15 sessions -> next-session open entry',
            'information_timing': 'A 3L/3R pivot is usable only after its right-side confirmation. The BSL anchor must be confirmed before the break. Event date itself cannot be a response or entry day. The POI is fixed before its retest. Every node must precede the planned entry.',
            'poisoned_families_excluded': ['daily-HL plus opening/prior-low acceptance', 'SSL-exhaustion reversal', 'official securities-lending pressure', 'lockup-release supply exhaustion', 'insider-reduction supply exhaustion'],
        },
        'support_gate': {
            'raw_canonical_events_each_year_min': 500,
            'canonical_seed_total_min': 1000,
            'canonical_seed_each_year_min': 300,
            'unique_symbols_min': 500,
        },
        'frozen_execution_if_authorized': {
            'entry': 'first daily open after reclaim',
            'stop': 'demand OB low * 0.99',
            'target': 'nearest unconsumed pre-entry right-confirmed daily swing high with planned RR >= 1.5',
            'exits': 'strict T+1 only; gap-aware conservative stop-first collision; time20; fee 0.20%; serial position per symbol',
        },
        'strategy_quality_gate': {
            'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0,
            'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70,
            'every_year_avg_net_positive': True, 't1_violations': 0,
        },
        'no_variant_rule': 'If support fails, close without outcomes. If the independent raw oracle differs, close without replay. If one frozen strict-T+1 replay fails any quality gate, close this ontology without selector, threshold, timing, stop, target, hold, calendar, or symbol variants.',
        'decision': 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v589_preregistration.json').write_text(text)
    LATEST.write_text(text)
    print(text)

if __name__ == '__main__':
    main()
