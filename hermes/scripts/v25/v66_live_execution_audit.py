#!/usr/bin/env python3
"""Audit SMC realtime monitor execution contracts: live T+1, field completeness, sample hygiene."""
from __future__ import annotations
import json, datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
MON = ROOT / 'smc_monitor'
OUT = ROOT / 'smc_audit/v66_live_execution_audit.json'


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def date_key(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def f(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def zone_bounds(p):
    raw = p.get('raw_pick') or {}
    zl = f(p.get('zone_low') or raw.get('zone_low') or raw.get('dz_low') or raw.get('execution_zone_low'))
    zh = f(p.get('zone_high') or raw.get('zone_high') or raw.get('dz_high') or raw.get('execution_zone_high'))
    if zl and zh and zl > zh:
        zl, zh = zh, zl
    return zl, zh


def main():
    positions = load(MON / 'positions.json', [])
    ledger = load(MON / 'trade_ledger.json', [])
    reviews = load(MON / 'closed_reviews.json', [])
    violations = {
        'same_day_fills': [],
        'ledger_same_day_buys': [],
        'open_missing_zone': [],
        'open_missing_cost_line': [],
        'open_missing_vol_class': [],
        'open_zone_invalid': [],
        'watch_only_missing_reason': [],
        'clean_missing_provenance': [],
        'production_review_pollution': [],
        'production_closed_position_pollution': [],
        'polluted_count': 0,
    }
    clean_count = 0
    for p in positions:
        status = p.get('status') or ''
        raw = p.get('raw_pick') or {}
        pick = date_key(p.get('pick_date') or raw.get('pick_date') or raw.get('select_date'))
        fill = date_key(p.get('filled_at') or (p.get('created_at') if status == 'OPEN' else ''))
        if status in ('OPEN', 'CLOSED', 'WATCH_ONLY') and pick and fill and fill <= pick and p.get('filled_at'):
            violations['same_day_fills'].append({'symbol': p.get('symbol'), 'status': status, 'pick_date': pick, 'filled_at': p.get('filled_at'), 'id': p.get('id')})
        sc = p.get('sample_class') or ''
        if sc == 'PRODUCTION_CLEAN':
            clean_count += 1
        elif status in ('OPEN', 'CLOSED', 'WATCH_ONLY'):
            violations['polluted_count'] += 1
        if status == 'OPEN':
            zl, zh = zone_bounds(p)
            if not (zl and zh):
                violations['open_missing_zone'].append(p.get('symbol'))
            if not f(p.get('cost_line') or raw.get('v25_cost_line')):
                violations['open_missing_cost_line'].append(p.get('symbol'))
            if not (p.get('vol_class') or raw.get('v25_vol_class') or raw.get('regime') or raw.get('market_state')):
                violations['open_missing_vol_class'].append(p.get('symbol'))
            rel = str(p.get('entry_zone_relation') or '')
            gate = p.get('production_gate') or {}
            reasons = gate.get('reasons') or []
            if rel.startswith('BELOW_ZONE') and any(str(r).startswith('PRICE_BELOW_ZONE') for r in reasons):
                violations['open_zone_invalid'].append({'symbol': p.get('symbol'), 'relation': rel, 'reasons': reasons})
            if rel.startswith('ABOVE_ZONE') and any(str(r).startswith('PRICE_ABOVE_ZONE') for r in reasons):
                violations['open_zone_invalid'].append({'symbol': p.get('symbol'), 'relation': rel, 'reasons': reasons})
            if sc == 'PRODUCTION_CLEAN' and (p.get('zone_idx') is None or p.get('conf_index') is None):
                violations['clean_missing_provenance'].append(p.get('symbol'))
        if status == 'WATCH_ONLY' and not (p.get('reject_reason') or p.get('pending_reason') or (p.get('production_gate') or {}).get('reasons')):
            violations['watch_only_missing_reason'].append(p.get('symbol'))
        if status == 'CLOSED' and sc != 'PRODUCTION_CLEAN':
            violations['production_closed_position_pollution'].append({'symbol': p.get('symbol'), 'id': p.get('id'), 'sample_class': sc})
    for r in reviews:
        if r.get('sample_class') != 'PRODUCTION_CLEAN':
            violations['production_review_pollution'].append({'symbol': r.get('symbol'), 'id': r.get('id'), 'sample_class': r.get('sample_class'), 'root_cause': r.get('root_cause')})
    for r in ledger:
        if r.get('invalidated'):
            continue
        if r.get('action') != 'BUY':
            continue
        pick = date_key(r.get('pick_date') or r.get('select_date'))
        buy = date_key(r.get('buy_date') or r.get('event_date'))
        if pick and buy and buy <= pick:
            violations['ledger_same_day_buys'].append({'symbol': r.get('symbol'), 'pick_date': pick, 'buy_date': buy, 'id': r.get('id')})
    pass_checks = {
        'live_t1_no_same_day_fill': not violations['same_day_fills'],
        'ledger_t1_no_same_day_buy': not violations['ledger_same_day_buys'],
        'open_zone_complete': not violations['open_missing_zone'],
        'open_cost_line_complete': not violations['open_missing_cost_line'],
        'open_vol_class_complete': not violations['open_missing_vol_class'],
        'open_zone_valid': not violations['open_zone_invalid'],
        'watch_only_has_reason': not violations['watch_only_missing_reason'],
        'clean_provenance_complete': not violations['clean_missing_provenance'],
        'production_reviews_clean_only': not violations.get('production_review_pollution'),
        'production_closed_positions_clean_only': not violations.get('production_closed_position_pollution'),
    }
    out = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'pass': all(pass_checks.values()),
        'checks': pass_checks,
        'positions_total': len(positions),
        'open_count': sum(1 for p in positions if p.get('status') == 'OPEN'),
        'watch_only_count': sum(1 for p in positions if p.get('status') == 'WATCH_ONLY'),
        'closed_count': sum(1 for p in positions if p.get('status') == 'CLOSED'),
        'production_clean_count': clean_count,
        'reviews_total': len(reviews),
        'violations': violations,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
