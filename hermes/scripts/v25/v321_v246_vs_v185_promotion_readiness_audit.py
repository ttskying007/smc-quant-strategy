#!/usr/bin/env python3
"""V321 no-write promotion-readiness audit: V248/V246 strong historical candidate vs V185.

V320 fresh daily supply failed. V248/V246 has a stronger historical gate, but prior
notes said current scanner smoke was required. This script consolidates the latest
independent historical audit and rerun current dry scanner reconstruction to decide
whether V248/V246 can replace V185 now. It writes audit artifacts only.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v321_v246_vs_v185_promotion_readiness_no_write_{TS}'
LATEST = AUD / 'v321_v246_vs_v185_promotion_readiness_latest.json'
V185 = ROOT / 'smc_opt_v185_combined_production_candidate/v185_report.json'
V248 = AUD / 'v248_v246_independent_audit_latest.json'
V246_CURRENT = max(AUD.glob('v246_daily_current_shadow_audit_no_write_*/*summary.json'), default=None)
if V246_CURRENT is None:
    # Script v246_daily_current_shadow_audit writes summary.json in its out dir.
    candidates = list(AUD.glob('v246_daily_current_shadow_audit_no_write_*'))
    V246_CURRENT = max(candidates, key=lambda p: p.stat().st_mtime) / 'summary.json' if candidates else None

PROMOTION_GATE = {
    'historical_n_min': 570,
    'historical_min_year_n_min': 70,
    'historical_wr_min': 93.0,
    'historical_avg_min': 7.6,
    'historical_year_wr_min': 91.0,
    'historical_micro_max': 1.0,
    't1': 0,
    'current_scanner_required': True,
    'selector_leak_fields': [],
}


def load(path: Path | None, default):
    if path is None:
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    v185 = load(V185, {})
    v248 = load(V248, {})
    cur = load(V246_CURRENT, {})
    selected = v248.get('selected', {})
    hist_pass = bool(v248.get('production_pass')) and selected.get('n',0) >= PROMOTION_GATE['historical_n_min'] and selected.get('min_year_n',0) >= PROMOTION_GATE['historical_min_year_n_min'] and selected.get('wr',0) >= PROMOTION_GATE['historical_wr_min'] and selected.get('avg',0) >= PROMOTION_GATE['historical_avg_min'] and selected.get('all_year_wr_min',0) >= PROMOTION_GATE['historical_year_wr_min'] and selected.get('micro_profit_pct',999) <= PROMOTION_GATE['historical_micro_max'] and selected.get('t1',0) == 0 and v248.get('selector_leak_fields') == []
    current_rows = int(cur.get('new_actionable_rows', 0) or 0)
    current_pass = cur.get('selector_leak_fields') == [] and cur.get('active_outcome_pollution', 0) == 0 and cur.get('time_order_bad_count', 0) == 0 and current_rows > 0
    decision = 'V321_READY_TO_PROMOTE_V246_OVER_V185' if hist_pass and current_pass else 'V321_HISTORICAL_PASS_BUT_CURRENT_SCANNER_NOT_ACTIONABLE__KEEP_V185'
    report = {
        'version': 'V321_V246_VS_V185_PROMOTION_READINESS_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'gate': PROMOTION_GATE,
        'v185_current_production': {
            'decision': v185.get('decision'),
            'metrics': v185.get('metrics') or v185.get('production_stats'),
            'active_pick_count': v185.get('active_pick_count'),
            'latest_market_date': v185.get('latest_market_date'),
        },
        'v248_v246_historical': {
            'source': str(V248),
            'decision': v248.get('decision'),
            'production_pass': v248.get('production_pass'),
            'selected': selected,
            'monthly': v248.get('monthly'),
            'rolling_100': v248.get('rolling_100'),
            'selector_fields': v248.get('selector_fields'),
            'selector_leak_fields': v248.get('selector_leak_fields'),
            'hard_failures': v248.get('hard_failures'),
        },
        'v246_current_scanner': {
            'source': str(V246_CURRENT) if V246_CURRENT else None,
            'decision': cur.get('decision'),
            'latest_market_date': cur.get('latest_market_date'),
            'dry_recent45_rows': cur.get('dry_recent45_rows'),
            'parent_raw_rule_rows': cur.get('parent_raw_rule_rows'),
            'raw_rule_rows': cur.get('raw_rule_rows'),
            'new_actionable_rows': cur.get('new_actionable_rows'),
            'selector_leak_fields': cur.get('selector_leak_fields'),
            'active_outcome_pollution': cur.get('active_outcome_pollution'),
            'time_order_bad_count': cur.get('time_order_bad_count'),
            'new_actionable_symbols': cur.get('new_actionable_symbols'),
        },
        'checks': {'historical_gate_pass': hist_pass, 'current_scanner_actionable_pass': current_pass},
        'decision': decision,
        'reason': 'V248/V246 historical metrics dominate V185, but latest direct current reconstruction has 0 raw/current actionable rows; do not switch production routing until current scanner emits valid non-overlap rows or route is explicitly intended as historical-only backtest view.',
        'artifacts': {'report': str(OUT / 'v321_report.json'), 'latest': str(LATEST)},
    }
    json.dump(report, open(OUT / 'v321_report.json','w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST,'w'), ensure_ascii=False, indent=2)
    print(json.dumps({'latest': str(LATEST), 'decision': decision, 'checks': report['checks'], 'v185_metrics': report['v185_current_production']['metrics'], 'v248_selected': selected, 'v246_current': report['v246_current_scanner']}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
