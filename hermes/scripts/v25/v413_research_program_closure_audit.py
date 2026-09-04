#!/usr/bin/env python3
"""V413 no-write research-program closure audit.

Collects only finalized audit reports to establish which information classes have
been tested, which passed source/PIT gates, which failed economic gates, and
which are still external-data blockers.  It does not generate candidates or
replay outcomes.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
OUT = AUD / f'v413_research_program_closure_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v413_research_program_closure_latest.json'

# Fixed registry: every branch must have a concrete audit artifact, otherwise it
# is not considered closed.  Class is the information content, not an endpoint.
BRANCHES = [
    ('daily_causal_smc', 'Raw daily causal SMC narratives (R1/R2/C1)', 'v411_combo_yearly_stability_latest.json', 'economic'),
    ('canonical_daily_continuation', 'Canonical daily BOS/OB continuation', 'v360_canonical_persistent_takeover_daily_t1_replay_latest.json', 'economic'),
    ('full_history_m60', 'Full historical 60-minute causal MTF entry', 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json', 'economic'),
    ('same_day_participation', 'Same-day cross-sectional participation', 'v383_pit_participation_outcome_replay_latest.json', 'economic'),
    ('prior_behavior_cohorts', 'Prior-20-session stock behavior cohorts', 'v385_pit_behavior_cohort_outcome_replay_latest.json', 'economic'),
    ('timed_disclosures', 'Exact-publication-time disclosures', 'v392_pit_disclosure_window_robustness_latest.json', 'economic'),
    ('dragon_tiger', 'Strict-prior-date 龙虎榜', 'v394_pit_lhb_outcome_replay_latest.json', 'economic'),
    ('margin_financing', 'Prior-completed-session financing/margin intensity', 'v395_pit_margin_financing_latest.json', 'economic'),
    ('top_shareholders', 'PIT top-10 shareholder snapshots', 'v403_pit_shareholder_frozen_outcome_replay_latest.json', 'economic'),
    ('block_trades', 'Strict-prior-date block trades', 'v405_pit_block_trade_frozen_outcome_replay_latest.json', 'economic'),
    ('northbound_holdings', 'Northbound holdings', 'v406_pit_northbound_holdings_availability_latest.json', 'availability'),
    ('historical_ticks', 'mootdx historical transaction/tick', 'v407_pit_tick_history_availability_latest.json', 'availability'),
    ('eastmoney_subhourly', 'Eastmoney 5/15/30-minute history', 'v408_eastmoney_intraday_history_availability_latest.json', 'availability'),
    ('baostock_subhourly', 'Baostock 5/15/30-minute history', 'v412_baostock_subhourly_access_latest.json', 'availability'),
    ('main_fund_flow', 'Eastmoney/AkShare main fund-flow history', 'v396_pit_main_flow_history_feasibility_latest.json', 'availability'),
    ('fund_holdings', 'Aggregate fund holdings snapshots', 'v397_pit_fund_holdings_availability_latest.json', 'availability'),
    ('etf_share_changes', 'Exchange ETF share changes / constituent mapping', 'v398_pit_etf_share_change_availability_latest.json', 'availability'),
]


def load(name: str) -> dict:
    path = AUD / name
    if not path.exists():
        return {'artifact_missing': True}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {'artifact_unreadable': f'{type(exc).__name__}: {exc}'}


def text_of(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False).lower()


def classify(kind: str, data: dict) -> tuple[str, str]:
    if data.get('artifact_missing') or data.get('artifact_unreadable'):
        return 'UNVERIFIED', 'missing/unreadable audit artifact'
    text = text_of(data)
    decision = str(data.get('decision', ''))
    if kind == 'availability':
        # Several older reports predate a uniform `availability_gate_pass` field;
        # their explicit STOP / NO_REPLAY decision is still a formal closure.
        unavailable_words = ('availability_fail', 'insufficient_history', 'timestamp_unproven',
                             'not_a_verifiable_pit', 'source_access_unavailable',
                             'tick_history_availability_fail', 'no_replay', 'branch_not_started')
        if (data.get('availability_gate_pass') is False
                or data.get('outcome_replay_allowed') is False
                or any(word in text for word in unavailable_words)):
            return 'CLOSED_UNAVAILABLE', decision or 'source/PIT/coverage gate failed'
        return 'UNVERIFIED', decision or 'availability report does not state a closure condition'
    # Economic branches must have opened a frozen replay and explicitly failed/
    # closed or reported no production pass; a source availability result alone
    # does not count as an economic closure.
    failure_words = ('no state passed', '0/6', 'failed', 'close', 'production pass": 0',
                     'no promotion', 'data gate fail', 'robustness_data_gate_fail')
    if any(word in text for word in failure_words):
        return 'CLOSED_ECONOMIC', decision or 'frozen economic gate did not pass'
    return 'UNVERIFIED', decision or 'economic closure not explicit in report'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for code, label, artifact, kind in BRANCHES:
        data = load(artifact)
        status, reason = classify(kind, data)
        rows.append({
            'branch': code, 'information_class': label, 'audit_type': kind,
            'artifact': str(AUD / artifact), 'artifact_version': data.get('version', ''),
            'status': status, 'reason': reason,
            'no_write': data.get('no_write'), 'outcome_replay_allowed': data.get('outcome_replay_allowed'),
        })
    counts = {status: sum(row['status'] == status for row in rows) for status in ('CLOSED_ECONOMIC', 'CLOSED_UNAVAILABLE', 'UNVERIFIED')}
    blockers = [row['information_class'] for row in rows if row['status'] == 'CLOSED_UNAVAILABLE']
    unverified = [row['information_class'] for row in rows if row['status'] == 'UNVERIFIED']
    report = {
        'version': 'V413_RESEARCH_PROGRAM_CLOSURE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'all free/local source classes explicitly audited through V412',
        'fixed_usefulness_gate': {
            'production_economic': 'n>=300; each year>=40; WR uplift>=5pp; AvgPnL uplift>=1pp; min-year WR uplift>=3pp; chronological epoch stability; T+1=0',
            'source_admission': 'full fixed-identity coverage; strict prior-time/publication PIT; raw source-price alignment; then one frozen-schema replay',
        },
        'counts': counts,
        'branch_registry': rows,
        'closed_economic_meaning': 'The class was source-valid and tested in a fixed causal replay, but failed the predeclared usefulness gate. Do not threshold/exit-mine it again.',
        'closed_unavailable_meaning': 'The source could not establish full history/PIT/coverage. No economic conclusion is permitted.',
        'unverified_classes': unverified,
        'external_blockers': blockers,
        'remaining_eligible_research': [
            'A provider/archive with full 2023-2026, date-addressable tick or order-book data and verifiable timestamps.',
            'A genuinely new stock-level point-in-time source with raw publication time, full V381 coverage, and a predeclared immutable feature schema.',
        ],
        'program_decision': ('RESEARCH_FRONTIER_CLOSED__NO_LEGITIMATE_EXISTING_DATA_ITERATION' if not unverified else 'CLOSURE_INCOMPLETE__UNVERIFIED_AUDIT_ARTIFACTS_EXIST'),
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v413_report.json').write_text(rendered)
    LATEST.write_text(rendered)
    print(rendered)


if __name__ == '__main__':
    main()
