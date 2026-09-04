#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

BASE_TRADES = Path('/root/.hermes/smc_opt_v86_production_gate/v86_trades.json')
BASE_PICKS = Path('/root/.hermes/smc_opt_v86_production_gate/v86_picks.json')
V87_ROWS = Path('/root/.hermes/smc_opt_v87_mtf_entry_rr_matrix/v87_matrix_rows.json')
OUT = Path('/root/.hermes/smc_opt_v89_recovery_known_target')
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V89_RECOVERY_KNOWN_TARGET_RESEARCH'
ENTRY_MODE = 'zone_limit'
SL_MODE = 'hybrid_tight'
# Fixed pre-declared RR legs: avoids inherited V86 liquidity_target semantics.
TP_MODE = 'micro_0_8_1_5_3'

# Candidate filters tested in one run. 60min-dependent filters are marked research-only
# because 60min cache does not cover full 2023-2026 production history.
FILTERS: List[Tuple[str, str, Callable[[Dict[str, Any]], bool]]] = [
    ('V89_A_DAILY_NO_RECOVERY_ACCUM', 'production_like_daily_only', lambda r: r.get('market_state') not in ('RECOVERY', 'ACCUMULATION')),
    ('V89_B_RECOVERY_REQUIRE_M60_BULL_OR_MIXED', 'research_uses_partial_60min', lambda r: r.get('market_state') != 'RECOVERY' or r.get('m60_state') in ('BULL_CONTINUATION', 'MIXED')),
    ('V89_C_RECOVERY_REQUIRE_MTF3', 'research_uses_partial_60min', lambda r: r.get('market_state') != 'RECOVERY' or num(r.get('mtf_score')) >= 3),
    ('V89_D_RECOVERY_REQUIRE_MTF2', 'research_uses_partial_60min', lambda r: r.get('market_state') != 'RECOVERY' or num(r.get('mtf_score')) >= 2),
]


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def date_key(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'cum': 0, 'avg_rr': 0, 'low_rr_rate': 0, 'sl_rate': 0, 'avg_mfe_r': 0, 'avg_mae_r': 0}
    n = len(rows)
    pnl = [num(r.get('pnl_pct')) for r in rows]
    rr = [num(r.get('rr')) for r in rows]
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in pnl) / n * 100, 2),
        'avg_pnl': round(sum(pnl) / n, 4),
        'cum': round(sum(pnl), 2),
        'avg_rr': round(sum(rr) / n, 4),
        'low_rr_rate': round(sum(x < 1 for x in rr) / n * 100, 2),
        'sl_rate': round(sum(str(r.get('exit_reason')) == 'SL_HIT' for r in rows) / n * 100, 2),
        'avg_mfe_r': round(sum(num(r.get('mfe_r')) for r in rows) / n, 4),
        'avg_mae_r': round(sum(num(r.get('mae_r')) for r in rows) / n, 4),
    }


def bucket(rows: List[Dict[str, Any]], key: Callable[[Dict[str, Any]], Any]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(groups.items())}


def apply_contract(base: Dict[str, Any], v87: Dict[str, Any], candidate: str, gate_type: str) -> Dict[str, Any]:
    row = dict(base)
    entry = num(v87.get('entry_price'))
    sl = num(v87.get('sl'))
    tp1 = num(v87.get('tp1'))
    tp2 = num(v87.get('tp2'))
    tp3 = num(v87.get('tp3'))
    risk_pct = (entry - sl) / entry * 100 if entry and sl else 0
    row.update({
        'engine': ENGINE,
        'signal_engine': base.get('engine') or 'V86_PRODUCTION_GATE',
        'contract_source': 'V86_SIGNAL_LAYER_PLUS_V87_FIXED_RR_KNOWN_TARGET_CONTRACT',
        'v89_candidate': candidate,
        'v89_gate_type': gate_type,
        'v89_repair': 'RECOVERY_FILTER_PLUS_FIXED_ENTRY_KNOWN_RR_TARGET',
        'v89_target_semantics': 'ENTRY_KNOWN_FIXED_RR_0_8_1_5_3_NO_FUTURE_LIQUIDITY_TARGET',
        'entry_mode': ENTRY_MODE,
        'sl_mode': SL_MODE,
        'tp_mode': TP_MODE,
        'entry_price_original_v86': round(num(base.get('entry_price')), 4),
        'entry_price': round(entry, 4),
        'price': round(entry, 4),
        'sl': round(sl, 4),
        'sl_price': round(sl, 4),
        'tp1': round(tp1, 4),
        'tp2': round(tp2, 4),
        'tp3': round(tp3, 4),
        'tp': round(tp1, 4),
        'tp1_price': round(tp1, 4),
        'risk_pct': round(risk_pct, 4),
        'risk_pct_v86': base.get('risk_pct'),
        'risk_pct_v87': v87.get('risk_pct_v87'),
        'rr': v87.get('rr'),
        'rr_realized': v87.get('rr_realized'),
        'exit_price': v87.get('exit_price'),
        'exit_reason': v87.get('exit_reason'),
        'pnl_pct': v87.get('pnl_pct'),
        'exit_legs': v87.get('exit_legs') or [],
        'mfe_pct': v87.get('mfe_pct'),
        'mae_pct': v87.get('mae_pct'),
        'mfe_r': v87.get('mfe_r'),
        'mae_r': v87.get('mae_r'),
        'weekly_state': v87.get('weekly_state'),
        'daily_state': v87.get('daily_state'),
        'm60_state': v87.get('m60_state'),
        'market_state': v87.get('market_state') or base.get('market_state'),
        'v85_market_substate': v87.get('v85_market_substate') or base.get('v85_market_substate'),
        'v85_path': v87.get('v85_path') or base.get('v85_path'),
        'mtf_score': v87.get('mtf_score'),
        'm60_entry_state': v87.get('m60_entry_state'),
        'planned_exit_signal': 'FIXED_RR_TP1_TP2_RUNNER_CONTRACT',
        'planned_exit_price': round(tp1, 4),
        'planned_exit_legs': [
            {'name': 'TP1_0_8R', 'price': round(tp1, 4), 'weight': 0.35},
            {'name': 'TP2_1_5R', 'price': round(tp2, 4), 'weight': 0.35},
            {'name': 'TP3_3R_RUNNER', 'price': round(tp3, 4), 'weight': 0.30},
        ],
        'smart_money_cost': round(num(base.get('smart_money_cost')) or (num(base.get('zone_low')) + num(base.get('zone_high'))) / 2 or entry, 4),
        'cost_line': round(num(base.get('cost_line') or base.get('smart_money_cost')) or (num(base.get('zone_low')) + num(base.get('zone_high'))) / 2 or entry, 4),
        'volatility_pct': round(num(base.get('volatility_pct') or base.get('v85_zone_width_pct') or risk_pct), 4),
        'zone_type': base.get('zone_type') or base.get('poi_type') or 'DEMAND_OB',
        'signal_type': base.get('signal_type') or base.get('zone_type') or base.get('poi_type') or 'DEMAND_OB',
        'pick_date': date_key(base.get('pick_date') or base.get('select_date') or base.get('event_date')),
        'select_date': date_key(base.get('select_date') or base.get('pick_date') or base.get('event_date')),
        'join_date': date_key(base.get('join_date') or base.get('entry_date')),
        'pick_scope': 'ACTIVE_CANDIDATE',
        'is_active_pick': True,
        'setup_status': 'V89_RESEARCH_CANDIDATE',
        'state': 'ACTIVE_CANDIDATE',
        'sample_class': 'RESEARCH_CLEAN',
        'sample_issue_flags': ['PARTIAL_60MIN_DEPENDENCY'] if gate_type.startswith('research') else [],
        't1_violation': bool(v87.get('t1_violation')),
    })
    return row


def build_candidate(candidate: str, gate_type: str, keep: Callable[[Dict[str, Any]], bool], base_trades, base_picks, chosen):
    v87_by_key = {(r.get('symbol'), date_key(r.get('entry_date'))): r for r in chosen if keep(r)}
    trades = []
    missing = []
    for b in base_trades:
        k = (b.get('symbol'), date_key(b.get('entry_date')))
        v = v87_by_key.get(k)
        if not v:
            continue
        trades.append(apply_contract(b, v, candidate, gate_type))
    pick_by_key = {(p.get('symbol'), date_key(p.get('entry_date'))): p for p in base_picks}
    picks = []
    for t in trades:
        k = (t.get('symbol'), date_key(t.get('entry_date')))
        v = v87_by_key.get(k)
        if not v:
            missing.append(k)
            continue
        p = apply_contract(pick_by_key.get(k, t), v, candidate, gate_type)
        p['source_trade_outcome'] = {'exit_reason': p.get('exit_reason'), 'pnl_pct': p.get('pnl_pct'), 'exit_legs': p.get('exit_legs')}
        picks.append(p)
    field_keys = ['engine','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','volatility_pct','entry_price','sl','tp1','tp2','tp3','rr','rr_realized','exit_legs','mfe_r','mae_r','weekly_state','daily_state','m60_state','mtf_score']
    field_audit = {k: sum(1 for r in trades if r.get(k) in (None, '') or (k in {'zone_low','zone_high','cost_line','entry_price','sl','tp1','tp2','tp3','rr'} and num(r.get(k)) <= 0)) for k in field_keys}
    report = {
        'engine': ENGINE,
        'candidate': candidate,
        'gate_type': gate_type,
        'source_signal_layer': str(BASE_TRADES),
        'source_contract_matrix': str(V87_ROWS),
        'combo': f'{ENTRY_MODE}|{SL_MODE}|{TP_MODE}',
        'target_semantics': 'fixed RR 0.8/1.5/3.0 computed before replay; no V86 liquidity_target inheritance',
        'trades': metrics(trades),
        'by_year': bucket(trades, lambda r: date_key(r.get('entry_date'))[:4]),
        'by_market_state': bucket(trades, lambda r: r.get('market_state')),
        'by_daily_state': bucket(trades, lambda r: r.get('daily_state')),
        'by_m60_state': bucket(trades, lambda r: r.get('m60_state')),
        'by_mtf_score': bucket(trades, lambda r: r.get('mtf_score')),
        'by_exit_reason': bucket(trades, lambda r: r.get('exit_reason')),
        'field_audit': field_audit,
        't1_violation_count': sum(1 for r in trades if r.get('t1_violation')),
        'missing_contract_keys': missing[:20],
    }
    m = report['trades']
    report['release_gate'] = {
        'wr_ge_90': m['wr'] >= 90,
        'avg_rr_ge_1_5': m['avg_rr'] >= 1.5,
        'rr_lt_1_zero': m['low_rr_rate'] == 0,
        'field_missing_zero': all(v == 0 for v in field_audit.values()),
        't1_zero': report['t1_violation_count'] == 0,
        'n_ge_500': m['n'] >= 500,
        'production_ready': False,
        'production_blocker': '60min history incomplete' if gate_type.startswith('research') else ('sample below 500' if m['n'] < 500 else '')
    }
    cdir = OUT / candidate
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / 'trades.json').write_text(json.dumps(trades, ensure_ascii=False, indent=2))
    (cdir / 'picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    (cdir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (cdir / 'trades.csv').open('w', newline='') as fp:
        fields = sorted({k for r in trades for k in r.keys()}) if trades else []
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(trades)
    return report


def main() -> None:
    base_trades = load(BASE_TRADES, [])
    base_picks = load(BASE_PICKS, [])
    v87_rows = load(V87_ROWS, [])
    chosen = [r for r in v87_rows if r.get('entry_mode') == ENTRY_MODE and r.get('sl_mode') == SL_MODE and r.get('tp_mode') == TP_MODE]
    reports = [build_candidate(name, gate_type, fn, base_trades, base_picks, chosen) for name, gate_type, fn in FILTERS]
    summary = {
        'engine': ENGINE,
        'tested_combo': f'{ENTRY_MODE}|{SL_MODE}|{TP_MODE}',
        'tested_candidates': [{
            'candidate': r['candidate'],
            'gate_type': r['gate_type'],
            **r['trades'],
            **{f'gate_{k}': v for k, v in r['release_gate'].items()}
        } for r in reports],
        'best_wr_candidate': max(reports, key=lambda r: r['trades']['wr'])['candidate'] if reports else '',
        'best_production_like_candidate': next((r['candidate'] for r in reports if r['gate_type'] == 'production_like_daily_only'), ''),
        'decision': 'RESEARCH_ONLY: 90%+ candidates either have <500 rows or depend on incomplete 60min history; do not promote over V88 production yet.'
    }
    (OUT / 'v89_summary_report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
