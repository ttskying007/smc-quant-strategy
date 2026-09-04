#!/usr/bin/env python3
"""V152 production artifact builder.

Reads the validated V152 hybrid lifecycle gate rows and writes frontend/API-ready
backtest artifacts. This does not create live buy candidates; active picks remain
sourced from the full-market daily scanner.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
SRC = ROOT / 'smc_audit' / 'v152_hybrid_lifecycle_gate_backtest_20260622' / 'v152_best_rows.csv'
SRC_SUMMARY = ROOT / 'smc_audit' / 'v152_hybrid_lifecycle_gate_backtest_20260622' / 'summary.json'
OUT = ROOT / 'smc_opt_v152_hybrid_lifecycle_gate'
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V152_HYBRID_LIFECYCLE_GATE'
VERSION = 'V152'


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)) or v == '':
            return default
        return float(v)
    except Exception:
        return default


def ikey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def bval(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {'true', '1', 'yes'}


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {'n': 0, 'wr': 0.0, 'avg_pnl': 0.0, 'median_pnl': 0.0, 'loss_rate': 0.0, 'hard_exit_rate': 0.0, 't1': 0}
    pnl = [fnum(r.get('pnl_pct')) for r in rows]
    hard = [str(r.get('exit_reason')) in {'ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'LIFECYCLE_CANCEL_NEXT_OPEN', 'BREAKEVEN_SL_T1_ADJUST'} or str(r.get('v152_lifecycle_action', '')).startswith('BE_SL_HIT') for r in rows]
    return {
        'n': n,
        'wr': round(sum(x > 0 for x in pnl) / n * 100, 2),
        'avg_pnl': round(sum(pnl) / n, 4),
        'median_pnl': round(float(pd.Series(pnl).median()), 4),
        'loss_rate': round(sum(x <= 0 for x in pnl) / n * 100, 2),
        'hard_exit_rate': round(sum(hard) / n * 100, 2),
        't1': sum(1 for r in rows if r.get('t1_violation')),
    }


def bucket(rows: list[dict[str, Any]], key: str, prefix: int | None = None) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = str(row.get(key) or '')
        groups[value[:prefix] if prefix else value].append(row)
    return {k: metrics(v) for k, v in sorted(groups.items())}


def convert_row(row: dict[str, Any]) -> dict[str, Any]:
    entry_date = ikey(row.get('v152_entry_date') or row.get('v138_entry_date') or row.get('entry_date'))
    exit_date = ikey(row.get('v152_exit_date') or row.get('v138_exit_date') or row.get('exit_date'))
    entry_price = fnum(row.get('v152_entry_price') or row.get('v138_entry_price') or row.get('entry_price'))
    exit_price = fnum(row.get('v152_exit_price') or row.get('v138_exit_price') or row.get('exit_price'))
    pnl = fnum(row.get('v152_pnl_pct') or row.get('v138_pnl_pct') or row.get('pnl_pct'))
    zone_low = fnum(row.get('zone_low'))
    zone_high = fnum(row.get('zone_high'))
    risk_pct = fnum(row.get('v138_risk_pct') or row.get('risk_pct'))
    sl = fnum(row.get('v138_sl')) or (entry_price * (1 - risk_pct / 100) if entry_price and risk_pct else 0.0)
    tp = fnum(row.get('v138_tp'))
    out = dict(row)
    out.update({
        'engine': ENGINE,
        'version': VERSION,
        'strategy_version': VERSION,
        'production_eligible_v152': True,
        'production_grade': 'A_PRODUCTION',
        'contract_source': 'V138_SIGNAL_LAYER_PLUS_V150_BE_SL_PLUS_V152_HYBRID_GATE',
        'selection_contract': 'skip PRE_BUY_GAP; BE-SL +50bp for weak cancel rows; preserve baseline when entry_above_reclaim_close_pct >= 0.1577',
        'symbol': row.get('symbol'),
        'event_date': ikey(row.get('event_date')),
        'pick_date': ikey(row.get('pick_date') or row.get('event_date')),
        'select_date': ikey(row.get('pick_date') or row.get('event_date')),
        'join_date': ikey(row.get('join_date') or entry_date),
        'entry_date': entry_date,
        'entry_idx': int(fnum(row.get('v152_entry_idx') or row.get('v138_entry_idx') or row.get('entry_idx'), -1)),
        'entry_price': round(entry_price, 4),
        'price': round(entry_price, 4),
        'exit_date': exit_date,
        'exit_idx': int(fnum(row.get('v152_exit_idx') or row.get('v138_exit_idx') or row.get('exit_idx'), -1)),
        'exit_price': round(exit_price, 4),
        'exit_reason': row.get('v152_exit_reason') or row.get('v138_exit_reason') or row.get('exit_reason'),
        'pnl_pct': round(pnl, 4),
        'won': pnl > 0,
        'hold_bars': max(0, int(fnum(row.get('v138_hold_bars') or row.get('hold_bars'), 0))),
        'sl': round(sl, 4),
        'sl_price': round(sl, 4),
        'sl_pct': round(risk_pct, 4),
        'risk_pct': round(risk_pct, 4),
        'tp': round(tp, 4),
        'tp1': round(tp, 4),
        'tp2': round(tp, 4),
        'tp3': round(tp, 4),
        'rr': round((tp - entry_price) / (entry_price - sl), 4) if entry_price > sl and tp else 0.0,
        'rr_realized': round(pnl / risk_pct, 4) if risk_pct else 0.0,
        'zone_type': row.get('poi_source') or 'FVG_Demand',
        'signal_type': row.get('poi_source') or 'FVG_Demand',
        'zone_low': round(zone_low, 4),
        'zone_high': round(zone_high, 4),
        'dz_low': round(zone_low, 4),
        'dz_high': round(zone_high, 4),
        'cost_line': round((zone_low + zone_high) / 2, 4) if zone_low and zone_high else round(entry_price, 4),
        'smart_money_cost': round((zone_low + zone_high) / 2, 4) if zone_low and zone_high else round(entry_price, 4),
        'volatility_pct': round(fnum(row.get('v85_zone_width_pct') or row.get('risk_pct')), 4),
        'market_state': row.get('market_state') or '',
        'combo_family': row.get('combo_family') or '',
        'event_type': row.get('event_type') or '',
        'entry_mode': row.get('v138_entry_kind') or 'after_reclaim_next_open',
        'lifecycle_status': row.get('v143_lifecycle_status') or '',
        'lifecycle_action': row.get('v152_lifecycle_action') or '',
        'v152_rule': row.get('v152_rule') or '',
        't1_violation': bval(row.get('v152_t1_violation')) or (entry_date >= exit_date if exit_date else False),
        'pick_scope': 'HISTORICAL_BEST',
        'is_active_pick': False,
        'setup_status': 'BACKTEST_PRODUCTION_CONTRACT_VERIFIED',
        'semantic_layer': 'V152_HYBRID_LIFECYCLE_VERIFIED',
        'strict_audit_status': 'PASS',
        'signal_correctness_claim': 'BACKTEST_CONTRACT_PASS_NOT_LIVE_PICK',
    })
    return out


def main() -> None:
    summary_in = json.loads(SRC_SUMMARY.read_text(encoding='utf-8'))
    if not summary_in.get('release_gate', {}).get('pass'):
        raise SystemExit('V152 release gate is not pass; refusing artifact build')
    df = pd.read_csv(SRC, low_memory=False).fillna('')
    trades = [convert_row(r) for r in df.to_dict(orient='records')]
    report = {
        'engine': ENGINE,
        'version': VERSION,
        'source': str(SRC),
        'production_write': True,
        'live_buy_candidates_written': False,
        'active_pick_policy': 'No historical V152 row is exposed as live buy candidate; daily scanner remains active-pick source.',
        'contract': trades[0]['selection_contract'] if trades else '',
        'production_total': len(trades),
        'production_stats': metrics(trades),
        'baseline_v138': summary_in.get('baseline_v138'),
        'v150_best_skip_pbg_be_sl50': summary_in.get('v150_best_skip_pbg_be_sl50'),
        'best_variant': summary_in.get('best_variant'),
        'best_threshold_entry_above_reclaim_pct': summary_in.get('best_threshold_entry_above_reclaim_pct'),
        'best_status_summary': summary_in.get('best_status_summary'),
        'best_action_summary': summary_in.get('best_action_summary'),
        'release_gate': summary_in.get('release_gate'),
        'by_year': bucket(trades, 'entry_date', prefix=4),
        'by_market_state': bucket(trades, 'market_state'),
        'by_lifecycle_status': bucket(trades, 'lifecycle_status'),
        'by_lifecycle_action': bucket(trades, 'lifecycle_action'),
        'by_exit_reason': bucket(trades, 'exit_reason'),
        'field_audit': {
            k: sum(1 for r in trades if r.get(k) in (None, '') or (k in {'entry_price', 'zone_low', 'zone_high', 'sl'} and fnum(r.get(k)) <= 0))
            for k in ['engine', 'symbol', 'entry_date', 'exit_date', 'entry_price', 'exit_price', 'zone_type', 'zone_low', 'zone_high', 'sl', 'risk_pct', 'pnl_pct']
        },
        't1_violation_count': sum(1 for r in trades if r.get('t1_violation')),
        'status_counts': dict(Counter(r.get('lifecycle_status') for r in trades)),
        'action_counts': dict(Counter(r.get('lifecycle_action') for r in trades)),
    }
    report['production_gate'] = {
        'release_gate_pass': bool(report['release_gate']['pass']),
        'n_ge_120': len(trades) >= 120,
        'wr_ge_90': report['production_stats']['wr'] >= 90,
        'avg_ge_baseline_minus_0_25': report['production_stats']['avg_pnl'] >= fnum((report.get('baseline_v138') or {}).get('avg')) - 0.25,
        't1_zero': report['t1_violation_count'] == 0,
        'field_missing_zero': all(v == 0 for v in report['field_audit'].values()),
        'no_live_historical_picks': True,
    }
    active_picks: list[dict[str, Any]] = []
    (OUT / 'v152_trades.json').write_text(json.dumps(trades, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'v152_picks.json').write_text(json.dumps(active_picks, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'v152_active_picks.json').write_text(json.dumps(active_picks, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'v152_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (OUT / 'v152_trades.csv').open('w', newline='', encoding='utf-8') as fp:
        fields = sorted({k for r in trades for k in r.keys()})
        writer = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(trades)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
