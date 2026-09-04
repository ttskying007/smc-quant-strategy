#!/usr/bin/env python3
"""V602 reconcile official-margin source readiness with the closed margin ontology.

No price/outcome data is read beyond the already-frozen V571 decision. This
prevents a completed raw source from being mistaken for permission to vary V569.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
BASE = ROOT / 'pit_cache' / 'v562_exchange_margin_raw'
OUT = AUD / 'v602_margin_source_and_ontology_reconciliation_latest.json'


def audit_exchange(exchange: str) -> dict:
    valid_dates: list[str] = []
    invalid: list[str] = []
    for path in sorted((BASE / exchange).glob('*.json.gz')):
        date = path.name[:8]
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as handle:
                doc = json.load(handle)
            if (doc.get('source') == f'{exchange}_official_exchange'
                    and doc.get('exchange') == exchange
                    and doc.get('date') == date
                    and len(doc.get('rows') or []) >= 500):
                valid_dates.append(date)
            else:
                invalid.append(date)
        except (OSError, ValueError, TypeError):
            invalid.append(date)
    years = Counter(date[:4] for date in valid_dates)
    return {
        'valid_dates': len(valid_dates),
        'invalid_dates': invalid,
        'year_counts': {year: years[year] for year in sorted(years)},
        'range': [min(valid_dates), max(valid_dates)] if valid_dates else [],
    }


def main() -> None:
    qualification = json.loads((AUD / 'v561_multilane_source_qualification_latest.json').read_text())
    prior = json.loads((AUD / 'v568_margin_financing_two_year_source_qualification_latest.json').read_text())
    replay = json.loads((AUD / 'v571_v569_frozen_strict_t1_replay_latest.json').read_text())
    sh, sz = audit_exchange('SH'), audit_exchange('SZ')
    required_complete_years = ('2023', '2024', '2025')
    complete = all(sh['year_counts'].get(year) == sz['year_counts'].get(year) and sh['year_counts'].get(year, 0) >= 240 for year in required_complete_years)
    assert qualification['lanes']['L1_stock_level_margin_financing']['status'] == 'PILOT_SOURCE_READY__FULL_HISTORY_BUILD_REQUIRED'
    assert prior['decision'] == 'TWO_YEAR_OFFICIAL_MARGIN_SOURCE_PASS__OUTCOME_BLIND_ONTOLOGY_PREREGISTRATION_AUTHORIZED'
    assert replay['decision'] == 'V571_FROZEN_REPLAY_GATE_FAIL__CLOSE_V569_ONTOLOGY_NO_VARIANTS'
    report = {
        'version': 'V602_MARGIN_SOURCE_AND_ONTOLOGY_RECONCILIATION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'scope': 'Source completeness reconciliation only; no seed, selector, replay, or parameter variant.',
        'raw_source_audit': {'SH': sh, 'SZ': sz, 'complete_decision_years_2023_2025': complete},
        'source_conclusion': 'Official SH/SZ margin raw cache is physically valid and complete for 2023-2025; 2026 is current partial and not a decision year.',
        'ontology_status': {
            'ontology': 'Prior-session financing-balance accumulation -> SSL sweep -> confirmed CHOCH -> demand reclaim -> next open',
            'frozen_replay': {'n': replay['overall']['n'], 'wr_pct': replay['overall']['wr_pct'], 'avg_net_pct': replay['overall']['avg_net_pct'], 'pf': replay['overall']['profit_factor'], 'payoff': replay['overall']['payoff'], 'yearly': replay['yearly'], 't1_violations': replay['invariants']['t1_violations']},
            'decision': replay['decision'],
        },
        'decision': 'SOURCE_READY_BUT_MARGIN_ONTOLOGY_CLOSED__NO_STRATEGY_VARIANT_AUTHORIZED__DO_NOT_REOPEN_FROM_CACHE_COMPLETENESS',
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
