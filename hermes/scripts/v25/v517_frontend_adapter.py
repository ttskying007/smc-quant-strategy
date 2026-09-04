#!/usr/bin/env python3
"""Read-only frontend adapter for the V517 effort-result research lineage.

This module materializes only audit artifacts and current scanner/shadow state.
It never writes production picks, watchlists, positions, frontend state, or trades.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KLINE = ROOT / 'kline_cache'
PENDING = ROOT / 'smc_monitor' / 'v526_pending_orders.json'
FILES = {
    'seed': AUD / 'v517_daily_effort_result_absorption_seed_gate_latest.json',
    'oracle': AUD / 'v518_daily_effort_result_absorption_independent_oracle_latest.json',
    'replay': AUD / 'v519_daily_effort_result_absorption_frozen_t1_replay_latest.json',
    'metric': AUD / 'v520_daily_effort_result_absorption_independent_metric_audit_latest.json',
    'scanner': AUD / 'v521_daily_effort_result_absorption_scanner_time_dry_run_latest.json',
    'release': AUD / 'v522_effort_result_release_audit_latest.json',
    'shadow': AUD / 'v523_effort_result_pending_next_open_shadow_latest.json',
    'rr_gate': AUD / 'v525_effort_result_structural_rr_gate_latest.json',
}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> str:
    return ''.join(ch for ch in str(value or '') if ch.isdigit())[:8]


def artifacts() -> dict[str, Any]:
    return {name: _load(path, {}) for name, path in FILES.items()}


def trades() -> list[dict[str, Any]]:
    replay = artifacts()['replay']
    source = Path((replay.get('artifacts') or {}).get('trades') or '')
    if not source.exists():
        return []
    rows: list[dict[str, Any]] = []
    with source.open(newline='') as handle:
        for raw in csv.DictReader(handle):
            entry = _num(raw.get('entry_price'))
            stop = _num(raw.get('stop'))
            target = _num(raw.get('target'))
            pnl = _num(raw.get('net_pnl_pct'))
            rows.append({
                **raw,
                'engine': 'V517_EFFORT_RESULT',
                'ontology': 'DAILY_EFFORT_RESULT_ABSORPTION',
                'signal_type': 'EFFORT_RESULT_ABSORPTION',
                'zone_type': 'HIGH_VOLUME_SSL_RECLAIM',
                'conf_type': 'RESPONSE_CLOSE_BREAKS_SWEEP_HIGH',
                'entry_mode': 'FOLLOWING_SESSION_OPEN_T1',
                'pick_date': _date(raw.get('response_date')),
                'signal_date': _date(raw.get('response_date')),
                'entry_date': _date(raw.get('entry_date')),
                'exit_date': _date(raw.get('exit_date')),
                'entry_price': entry,
                'exit_price': _num(raw.get('exit_price')),
                'sl_price': stop,
                'sl': stop,
                'stop': stop,
                'tp1': target,
                'tp_price': target,
                'target': target,
                'entry_type': 'FOLLOWING_SESSION_OPEN_T1',
                'signal_price': _num(raw.get('sweep_close')),
                'zone_low': _num(raw.get('sweep_low')),
                'zone_high': _num(raw.get('sweep_high') or raw.get('sweep_close')),
                'risk_pct': round((entry - stop) / entry * 100, 4) if entry and stop else 0,
                'sl_pct': round((entry - stop) / entry * 100, 4) if entry and stop else 0,
                'tp_pct': round((target - entry) / entry * 100, 4) if entry and target else 0,
                'planned_rr': round((target - entry) / (entry - stop), 4) if entry > stop and target else 0,
                'rr': round((target - entry) / (entry - stop), 4) if entry > stop and target else 0,
                'combo': 'SWING_LOW→HIGH_VOLUME_SSL_SWEEP_RECLAIM→RESPONSE_BREAK→T+1_ENTRY',
                'combo_contract': 'V517_FROZEN_REPLAY_READ_ONLY',
                'pnl_pct': pnl,
                'won': pnl > 0,
                'exit_reason': raw.get('reason') or '',
                'hold_bars': int(_num(raw.get('hold_bars'))),
                'prior20_volume_rank': _num(raw.get('prior20_volume_rank')),
                'causal_trace': raw.get('causal_trace') or '',
                'same_day_exit_violation': str(raw.get('same_day_exit_violation')).lower() == 'true',
                'trade_action': 'REPLAY_ONLY',
                'tradable': False,
                'buy_enabled': False,
            })
    return rows


def period_metrics() -> dict[str, Any]:
    replay = artifacts()['replay']
    path = Path((replay.get('artifacts') or {}).get('period_metrics') or '')
    return _load(path, {}) if path.exists() else {}


def _year_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [{'year': year, **values} for year, values in sorted((report.get('yearly') or {}).items())]


def _normalized_yearly(period: dict[str, Any], replay: dict[str, Any]) -> list[dict[str, Any]]:
    values = period.get('yearly') or replay.get('yearly') or {}
    if isinstance(values, dict):
        return _year_rows({'yearly': values})
    if isinstance(values, list):
        return [{**row, 'year': row.get('year') or row.get('entry_year'), 'n': row.get('n', row.get('trade_count'))}
                for row in values if isinstance(row, dict)]
    return []


def _exit_analysis(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row.get('exit_reason') or 'UNKNOWN'].append(row)
    out = []
    for reason, group in sorted(groups.items()):
        pnls = [_num(x.get('pnl_pct')) for x in group]
        out.append({'exit_reason': reason, 'n': len(group), 'wr_pct': round(sum(x > 0 for x in pnls) / len(pnls) * 100, 4), 'avg_net_pnl_pct': round(sum(pnls) / len(pnls), 4)})
    return out


def bundle() -> dict[str, Any]:
    a = artifacts()
    release = a['release']
    replay = a['replay']
    scanner = a['scanner']
    shadow = a['shadow']
    rows = trades()
    durable_pending = _load(PENDING, [])
    pending = [row for row in durable_pending if isinstance(row, dict) and row.get('status') == 'PENDING_NEXT_OPEN']
    scanner_rows = list(scanner.get('rows') or [])
    pending_source = 'DURABLE_PENDING_SNAPSHOT' if pending else 'NONE'
    blocked_current_candidates = []
    if not pending and release.get('production_license_granted') is True:
        pending = list((release.get('current_scanner') or {}).get('pending_rows') or scanner_rows)
        pending_source = 'CURRENT_RELEASE_SCANNER_SNAPSHOT'
    elif not pending:
        blocked_current_candidates = scanner_rows
    validations = list(shadow.get('validations') or [])
    picks = []
    for row in pending:
        picks.append({
            **row, 'engine': 'V517_EFFORT_RESULT', 'signal_type': 'EFFORT_RESULT_ABSORPTION',
            'zone_type': 'HIGH_VOLUME_SSL_RECLAIM', 'conf_type': 'RESPONSE_CLOSE_BREAKS_SWEEP_HIGH',
            'pick_date': _date(row.get('response_date')), 'entry_date': '', 'entry_price': 0,
            'tp1': _num(row.get('target')), 'sl_price': _num(row.get('stop')), 'trade_action': 'NO_BUY_PENDING_NEXT_OPEN',
            'tradable': False, 'buy_enabled': False,
        })
    for row in validations:
        if row.get('state') == 'SHADOW_BUY_VALID':
            picks.append({
                **row, 'engine': 'V517_EFFORT_RESULT', 'signal_type': 'EFFORT_RESULT_ABSORPTION',
                'zone_type': 'HIGH_VOLUME_SSL_RECLAIM', 'conf_type': 'EXACT_NEXT_OPEN_SHADOW_VALID',
                'pick_date': _date(row.get('response_date')), 'entry_date': _date(row.get('execution_epoch_date')),
                'entry_price': _num(row.get('entry_price')), 'tp1': _num(row.get('target')), 'sl_price': _num(row.get('stop')),
                'trade_action': 'NO_BUY_SHADOW_VALID_AWAIT_RELEASE', 'tradable': False, 'buy_enabled': False,
            })
    period = period_metrics()
    metrics = period.get('overall') or release.get('metrics') or replay.get('overall') or {}
    return {
        'version': 'V517_EFFORT_RESULT',
        'ontology': 'DAILY_EFFORT_RESULT_ABSORPTION',
        'research_result': release.get('research_result'),
        'live_release_state': release.get('live_release_state'),
        'live_release_rule': release.get('live_release_rule'),
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'buy_enabled': False,
        'trade_action': 'NO_BUY_RESEARCH_SHADOW_ONLY',
        'frozen_contract': a['seed'].get('frozen_contract'),
        'metrics': metrics,
        'yearly': _normalized_yearly(period, replay),
        'monthly': period.get('monthly') or [],
        'monthly_stability': period.get('monthly_stability') or {},
        'period_report_contract': period.get('entry_date_metric_contract') or '',
        'support': {'seed_count': a['seed'].get('seed_count'), 'yearly_seed_count': a['seed'].get('yearly_seed_count'), 'file_stats': a['seed'].get('file_stats'), 'invariants': a['seed'].get('invariants')},
        'oracle': {'generator_seed_count': a['oracle'].get('generator_seed_count'), 'oracle_seed_count': a['oracle'].get('oracle_seed_count'), 'missing_from_oracle_count': a['oracle'].get('missing_from_oracle_count'), 'extra_from_oracle_count': a['oracle'].get('extra_from_oracle_count'), 'oracle_pass': a['oracle'].get('oracle_pass')},
        'audit': {'checks': release.get('checks'), 'metric_invariants': a['metric'].get('invariants'), 'trade_integrity': release.get('trade_integrity')},
        'scanner': {'epoch_id': scanner.get('epoch_id'), 'market_date': scanner.get('market_date'), 'pending_next_open_count': len(pending), 'buy_valid_count': scanner.get('buy_valid_count'), 'decision': scanner.get('decision'), 'pending_source': pending_source, 'diagnostic_funnel': scanner.get('diagnostic_funnel') or {}},
        'blocked_current_candidates': [{
            **row,
            'trade_action': 'RESEARCH_BLOCKED_NOT_EXECUTABLE',
            'tradable': False,
            'buy_enabled': False,
            'blocked_reason': release.get('decision') or scanner.get('decision'),
        } for row in blocked_current_candidates],
        'shadow': {'epoch': shadow.get('epoch'), 'pending_snapshot_count': shadow.get('pending_snapshot_count'), 'validations': shadow.get('validations'), 'decision': shadow.get('decision')},
        'rr_feasibility': {'decision': a['rr_gate'].get('decision'), 'source_seed_count': a['rr_gate'].get('source_seed_count'), 'feasible_seed_count': a['rr_gate'].get('feasible_seed_count'), 'preentry_year_counts': a['rr_gate'].get('preentry_year_counts'), 'support_checks': a['rr_gate'].get('support_checks'), 'overall': a['rr_gate'].get('overall')},
        'picks': picks,
        'trades': rows,
        'analysis': {'exit_reason': _exit_analysis(rows), 'closed_trade_count': len(rows), 'nontradable_or_serial_skip_counts': replay.get('nontradable_or_serial_skip_counts')},
        'resonance': {
            'layers': [
                {'layer': '结构位置', 'event': 'confirmed 3L/3R swing low visible before sweep', 'state': 'REQUIRED'},
                {'layer': '量价吸收', 'event': '>=0.3% SSL breach + reclaim + prior20 volume top quintile', 'state': 'REQUIRED'},
                {'layer': '价格结果', 'event': 'next completed close breaks sweep high', 'state': 'REQUIRED'},
                {'layer': '执行时序', 'event': 'following-session open; strict T+1; shadow exact epoch', 'state': 'REQUIRED'},
            ],
            'note': '这是同周期的因果共振链，不冒充未经验证的周线/60分钟共振。'
        },
        'artifacts': {name: str(path) for name, path in FILES.items()},
    }


def _visual_smc_overlay(raw: list[dict[str, Any]], date_to_idx: dict[str, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Display-only Pine-like SMC context. Never contributes a V517 entry or replay row."""
    try:
        import sys
        here = str(Path(__file__).parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import smc_core_pine_like as pine
        groups = pine.detect_all_signals_pine_like(raw, timeframe='daily').get('signals', {})
    except Exception:
        return [], []
    signals, swings = [], []
    def add(kind, row, family, price=None, upper=None, lower=None):
        idx = int(row.get('index', row.get('idx', -1)) or -1)
        day = _date(row.get('date'))
        if day in date_to_idx:
            idx = date_to_idx[day]
        if idx < 0 or idx >= len(raw):
            return
        p = _num(price if price is not None else row.get('price', row.get('mid', row.get('break_price'))))
        signals.append({'seq': 0, 'type': kind, 'idx': idx, 'date': day, 'price': p,
                        'upper': _num(upper if upper is not None else row.get('zone_high', p)),
                        'lower': _num(lower if lower is not None else row.get('zone_low', p)),
                        'direction': row.get('direction', 'bull'), 'strength': row.get('confidence', 0.6),
                        'confidence': row.get('confidence', 0.6), 'family': family,
                        'display_only': True, 'source': 'PINE_LIKE_VISUAL_CONTEXT'})
    for direction, key in (('bull', 'highs'), ('bear', 'lows')):
        for row in (groups.get('swings') or {}).get(key, []):
            idx = int(row.get('idx', -1) or -1)
            if 0 <= idx < len(raw):
                label = row.get('label') or ('H' if key == 'highs' else 'L')
                swings.append({'bar': idx, 'type': 'HIGH' if key == 'highs' else 'LOW', 'price': _num(row.get('price')), 'label': label, 'rule': 'confirmed Pine-like swing; visual context only'})
    for row in groups.get('structure', []):
        add(f"{row.get('type', 'BOS')}_{'Bull' if row.get('direction') == 'bull' else 'Bear'}", row, 'structure', row.get('break_price', row.get('price')))
    for row in groups.get('fvgs', []):
        add(f"FVG_{'Bull' if row.get('direction') == 'bull' else 'Bear'}", row, 'fvg')
    for row in groups.get('obs', []):
        add(f"OB_{'Bull' if row.get('direction') == 'bull' else 'Bear'}", row, 'ob')
    for row in groups.get('sweeps', []):
        add('Sweep_' + row.get('subtype', 'SSL'), row, 'sweep', row.get('wick_low', row.get('wick_high', row.get('price'))))
    for row in groups.get('otes', []):
        add(f"OTE_{'Bull' if row.get('direction') == 'bull' else 'Bear'}", row, 'ote')
    for row in groups.get('eqh_eql', []):
        add('EQL_High' if row.get('type') == 'EQH' else 'EQL_Low', row, 'eql', row.get('level', row.get('price')))
    signals.sort(key=lambda x: (x['idx'], x['family'], x['type']))
    for i, row in enumerate(signals, 1):
        row['seq'] = i
    swings.sort(key=lambda x: x['bar'])
    return signals, swings


def kline(symbol: str) -> dict[str, Any]:
    symbol = str(symbol or '').upper()
    code, exchange = (symbol.split('.') + [''])[:2]
    raw = _load(KLINE / f'{code}_{exchange}_daily_750.json', [])
    klines = []
    for row in raw if isinstance(raw, list) else []:
        day = _date(row.get('t') or row.get('date') or row.get('day'))
        if day:
            klines.append({'date': day, 't': day, 'o': _num(row.get('o')), 'h': _num(row.get('h')), 'l': _num(row.get('l')), 'c': _num(row.get('c')), 'v': _num(row.get('v'))})
    date_to_idx = {row['date']: idx for idx, row in enumerate(klines)}
    selected = [row for row in trades() if row.get('symbol') == symbol]
    signals, swings = _visual_smc_overlay(raw if isinstance(raw, list) else [], date_to_idx)
    highlights = []
    for trade in selected:
        events = [
            ('SWING_LOW', trade.get('swing_date'), _num(trade.get('swing_low')), 'sweep'),
            ('HIGH_VOLUME_SSL_SWEEP_RECLAIM', trade.get('sweep_date'), _num(trade.get('sweep_low')), 'sweep'),
            ('RESPONSE_BREAKS_SWEEP_HIGH', trade.get('response_date'), _num(trade.get('response_close')), 'bos'),
            ('T1_ENTRY_OPEN', trade.get('entry_date'), _num(trade.get('entry_price')), 'bos'),
        ]
        for seq, (kind, day, price, family) in enumerate(events, 1):
            idx = date_to_idx.get(_date(day), -1)
            if idx >= 0:
                signals.append({'seq': len(signals) + 1, 'type': kind, 'idx': idx, 'date': _date(day), 'price': price, 'upper': price, 'lower': price, 'direction': 'bull', 'strength': 0.95, 'confidence': 1.0, 'family': family})
                highlights.append({'bar': idx, 'num': seq, 'type': kind})
        trade['_chart_idx'] = date_to_idx.get(trade.get('entry_date'), -1)
        trade['_exit_idx'] = date_to_idx.get(trade.get('exit_date'), trade['_chart_idx'])
        trade['_combo'] = 'SWING→VOLUME_SSL_RECLAIM→RESPONSE→T1_ENTRY'
        trade['_tt'] = trade.get('causal_trace') or ''
    return {'klines': klines, 'count': len(klines), 'signals_list': signals, 'signal_count': len(signals), 'swings': swings, 'wave_swings': swings, 'swing_count': len(swings), 'trades': selected, 'trade_count': len(selected), 'highlight': highlights, 'seq': '视觉 SMC 上下文（Swing/OB/FVG/Sweep/BOS） + V517：confirmed swing low → high-volume SSL reclaim → response break → following-session open', 'symbol': symbol, 'tf': 'daily', 'version': 'V517_EFFORT_RESULT', 'frontend_version': 'V517_REPLAY_GATE_FAILED_NO_BUY'}
