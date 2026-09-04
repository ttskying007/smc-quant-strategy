#!/usr/bin/env python3
"""V312 production/closed-branch consolidated status checkpoint.

No strategy change. No frontend/watchlist write. This combines the refreshed V185
production state, V246/V247 current shadow state, and V311 rejected intraday
branch into one audit checkpoint for continuation.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V185_DIR = BASE / 'smc_opt_v185_combined_production_candidate'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v312_production_shadow_branch_checkpoint_no_write_{TS}'
LATEST = AUDIT / 'v312_production_shadow_branch_checkpoint_latest.json'


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def dkey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v in ('', None):
            return default
        return float(v)
    except Exception:
        return default


def active_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcome_fields = {'exit_date', 'exit_idx', 'exit_price', 'exit_reason', 'hold_bars', 'mae_pct', 'mfe_pct', 'pnl_pct', 'rr_realized', 'won', 'partial_taken'}
    pollution = sum(1 for r in rows for k in outcome_fields if r.get(k) not in ('', None, False))
    by_date = Counter(dkey(r.get('pick_date') or r.get('entry_date') or r.get('select_date')) for r in rows)
    sample = []
    for r in rows[:20]:
        sample.append({
            'symbol': r.get('symbol'),
            'name': r.get('name') or r.get('stock_name'),
            'pick_date': dkey(r.get('pick_date') or r.get('entry_date') or r.get('select_date')),
            'engine': r.get('engine'),
            'status': r.get('status') or r.get('setup_status') or r.get('monitor_status'),
            'entry_price': r.get('entry_price'),
            'sl': r.get('sl') or r.get('stop_loss'),
            'tp1': r.get('tp1'),
            'tp2': r.get('tp2'),
        })
    return {'count': len(rows), 'active_outcome_pollution': pollution, 'by_pick_date': dict(by_date), 'sample': sample}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v185 = load(AUDIT / 'v185_daily_rematerialize_latest.json', {})
    v246 = load(AUDIT / 'v246_daily_current_shadow_audit_latest.json', {})
    v247 = load(AUDIT / 'v247_v246_current_smoke_latest.json', {})
    v311 = load(AUDIT / 'v311_v309_rule_walkforward_failure_attribution_latest.json', {})
    active = load(V185_DIR / 'v185_active_picks.json', [])
    report = load(V185_DIR / 'v185_report.json', {})
    trades = load(V185_DIR / 'v185_trades.json', [])
    same_day = sum(1 for r in trades if dkey(r.get('entry_date')) and dkey(r.get('entry_date')) == dkey(r.get('exit_date')))
    summary = {
        'version': 'V312_PRODUCTION_SHADOW_BRANCH_CHECKPOINT_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'production': {
            'active_version': 'V185',
            'engine': v185.get('engine') or report.get('engine'),
            'last_rematerialized_at': v185.get('generated_at') or report.get('last_rematerialized_at'),
            'metrics': v185.get('metrics') or report.get('metrics') or report.get('production_stats'),
            'active': active_summary(active),
            'same_day_exit_violations': same_day,
            'decision': 'KEEP_V185_PRODUCTION',
        },
        'shadow': {
            'v246_decision': v246.get('decision'),
            'v246_latest_market_date': v246.get('latest_market_date'),
            'v246_new_actionable_rows': v246.get('new_actionable_rows'),
            'v246_selector_leak_fields': v246.get('selector_leak_fields'),
            'v247_decision': v247.get('decision'),
            'decision': 'KEEP_V246_SHADOW_NO_WRITE',
        },
        'closed_research_branches': {
            'v309_v310_v311_intraday_leadership': {
                'decision': v311.get('closure', {}).get('decision'),
                'stable_rules_count': v311.get('stable_rules_count'),
                'dedup_candidate_rows': v311.get('coverage', {}).get('dedup_candidate_rows'),
                'baseline_wr': v311.get('baseline_dedup_candidate', {}).get('wr'),
                'baseline_avg': v311.get('baseline_dedup_candidate', {}).get('avg'),
                't1_violations': v311.get('baseline_dedup_candidate', {}).get('t1_violations'),
            }
        },
        'release_gate': {
            'can_claim_current_production_closed': bool(
                v185.get('ok') is True
                and same_day == 0
                and active_summary(active)['active_outcome_pollution'] == 0
                and v246.get('new_actionable_rows') == 0
                and v311.get('stable_rules_count') == 0
            ),
            'blocking_items': [],
            'next_action': 'Continue daily V185 production monitoring; keep V246 shadow and V309/V310 rejected branch out of production.',
        },
        'artifacts': {
            'summary': str(OUT / 'v312_summary.json'),
            'latest': str(LATEST),
            'v185_latest': str(AUDIT / 'v185_daily_rematerialize_latest.json'),
            'v246_latest': str(AUDIT / 'v246_daily_current_shadow_audit_latest.json'),
            'v247_latest': str(AUDIT / 'v247_v246_current_smoke_latest.json'),
            'v311_latest': str(AUDIT / 'v311_v309_rule_walkforward_failure_attribution_latest.json'),
        },
    }
    if not summary['release_gate']['can_claim_current_production_closed']:
        if v185.get('ok') is not True:
            summary['release_gate']['blocking_items'].append('V185 rematerialize latest not ok')
        if same_day:
            summary['release_gate']['blocking_items'].append(f'V185 same-day exit violations={same_day}')
        if active_summary(active)['active_outcome_pollution']:
            summary['release_gate']['blocking_items'].append('V185 active picks contain historical outcome fields')
        if v246.get('new_actionable_rows') != 0:
            summary['release_gate']['blocking_items'].append('V246 has current actionable rows needing review')
        if v311.get('stable_rules_count') != 0:
            summary['release_gate']['blocking_items'].append('V311 rejected branch unexpectedly has stable rules')
    (OUT / 'v312_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
