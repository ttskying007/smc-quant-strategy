#!/usr/bin/env python3
"""Freeze V591 before evaluating any earnings-response seed or outcome."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
LATEST = AUDIT / 'v591_earnings_attention_volume_fvg_preregistration_latest.json'
OUT = AUDIT / f'v591_earnings_attention_volume_fvg_preregistration_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    report = {
        'version': 'V591_EARNINGS_ATTENTION_VOLUME_FVG_PREREGISTRATION',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'purpose': 'A distinct event-attention and displacement ontology. It does not infer earnings direction from a title: it requires post-publication market confirmation through relative-volume bullish external BSL displacement and a contemporaneous bullish FVG, then buys only its later retest/reclaim.',
        'source_contract': {
            'metadata': '/root/.hermes/smc_audit/v563_pit_event_archive_full_coverage_no_outcome_20260724_124935/v563_event_metadata.jsonl',
            'allowed_metadata_fields': ['symbol', 'announcement_id', 'kind', 'notice_date', 'publication_time', 'title'],
            'event_rule': 'kind=EARNINGS_PREANNOUNCEMENT; title contains one of 业绩预告|业绩快报; one earliest source document per symbol and notice date.',
            'price_source': '/root/.hermes/kline_cache/*_daily_750.json including OHLCV only through planned entry',
            'years': ['2023', '2024', '2025'], 'same_day_execution_forbidden': True,
        },
        'causal_contract': {
            'sequence': 'PIT_EARNINGS_DISCLOSURE -> within next 5 sessions, bullish close above a 3L/3R-confirmed external BSL and volume >= 1.5x mean of preceding 20 sessions -> same-session bullish FVG -> FVG retest and close reclaim within next 15 sessions -> next-session open entry',
            'information_timing': 'A BSL pivot is valid only after its right-side confirmation and must be confirmed before the displacement close. The pre-break volume mean only uses sessions preceding the displacement bar. FVG bounds are fixed at displacement. Event date itself cannot be response or entry. Every causal node precedes entry.',
            'poi': 'bullish FVG (low of displacement bar minus high two bars earlier) created by a relative-volume external BSL displacement, not a demand OB and not an SSL/opening-range condition.',
            'poisoned_families_excluded': ['SSL-exhaustion reversal', 'daily-HL opening/prior-low acceptance', 'demand-OB retest after buyback commitment', 'official securities-lending pressure', 'lockup/reduction supply exhaustion'],
        },
        'support_gate': {'raw_canonical_events_each_year_min': 1500, 'canonical_seed_total_min': 1500, 'canonical_seed_each_year_min': 400, 'unique_symbols_min': 700},
        'frozen_execution_if_authorized': {'entry': 'first daily open after FVG reclaim', 'stop': 'FVG low * 0.99', 'target': 'nearest unconsumed pre-entry right-confirmed daily swing high with planned RR >= 1.5', 'exits': 'strict T+1 only; gap-aware conservative stop-first collision; time20; fee 0.20%; serial position per symbol'},
        'strategy_quality_gate': {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.50, 'pf_min': 1.15, 'payoff_min': 0.70, 'every_year_avg_net_positive': True, 't1_violations': 0},
        'no_variant_rule': 'Support fail closes without outcomes. Oracle mismatch closes without replay. A frozen strict-T+1 quality failure closes the ontology without selector, threshold, timing, stop, target, hold, calendar, or symbol variants.',
        'decision': 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v591_preregistration.json').write_text(text); LATEST.write_text(text); print(text)

if __name__ == '__main__': main()
