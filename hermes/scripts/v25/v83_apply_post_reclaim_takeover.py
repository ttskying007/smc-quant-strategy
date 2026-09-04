#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v81_full_market_scan import simulate_trade, f
from v83_post_reclaim_takeover_gate import evaluate_post_reclaim_takeover, apply_v83_entry

SRC = Path('/root/.hermes/smc_opt_v82_smart_money_quality_gate/v82_selected_candidates.json')
KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v83_post_reclaim_takeover')
OUT.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rs = list(rows)
    if not rs:
        return {'n': 0, 'wr': 0, 'avg_pnl': 0, 'cum': 0, 'poi_break_rate': 0, 'trend_damage_rate': 0, 'tp_rate': 0, 'time_stop_rate': 0}
    vals = [f(r.get('pnl_pct')) for r in rs]
    n = len(rs)
    return {
        'n': n,
        'wr': round(sum(v > 0 for v in vals) / n * 100, 2),
        'avg_pnl': round(sum(vals) / n, 4),
        'cum': round(sum(vals), 2),
        'poi_break_rate': round(sum(r.get('exit_reason') == 'EXIT_POI_CLOSE_BREAK' for r in rs) / n * 100, 2),
        'trend_damage_rate': round(sum(r.get('exit_reason') == 'EXIT_TREND_STRUCTURE_DAMAGE' for r in rs) / n * 100, 2),
        'tp_rate': round(sum(r.get('exit_reason') == 'TAKE_PROFIT_LIQUIDITY_TARGET' for r in rs) / n * 100, 2),
        'time_stop_rate': round(sum(r.get('exit_reason') == 'TIME_STOP_NO_SEMANTIC_EXIT' for r in rs) / n * 100, 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def main() -> None:
    rows = load_json(SRC)
    kcache: Dict[str, List[Dict[str, Any]]] = {}
    annotated: List[Dict[str, Any]] = []
    selected: List[Dict[str, Any]] = []
    missing_kline = 0

    for r in rows:
        sym = str(r.get('symbol'))
        if sym not in kcache:
            path = kline_path(sym)
            if not path.exists():
                kcache[sym] = []
            else:
                kcache[sym] = load_json(path)
        ks = kcache[sym]
        if not ks:
            nr = dict(r)
            nr.update({'v83_takeover_valid': False, 'v83_takeover_type': 'MISSING_KLINE'})
            annotated.append(nr)
            missing_kline += 1
            continue
        ft = evaluate_post_reclaim_takeover(r, ks)
        nr = apply_v83_entry(r, ks, ft)
        nr['v83_quality_gate'] = bool(ft.get('v83_takeover_valid'))
        if nr['v83_quality_gate']:
            nr = simulate_trade(nr, ks)
            nr['v83_quality_gate'] = True
            nr.update(ft)
            selected.append(nr)
        annotated.append(nr)

    report = {
        'engine': 'V83_POST_RECLAIM_TAKEOVER',
        'source': str(SRC),
        'rules': {
            'base': 'V82 selected only',
            'post_reclaim': 'after reclaim require 1-3 bars hold above POI or print higher low',
            'reject': 'POI close break, micro-HL break, no takeover, no next open after takeover',
            'entry': 'entry is moved to next open after takeover confirmation, T+1 simulated by v81 simulate_trade',
        },
        'metrics': {
            'v82_source': metrics(rows),
            'v83_selected': metrics(selected),
        },
        'year': bucket(selected, lambda r: str(r.get('entry_date', ''))[:4]),
        'story': bucket(selected, lambda r: r.get('story')),
        'market_state': bucket(selected, lambda r: r.get('market_state')),
        'takeover_type': bucket(selected, lambda r: r.get('v83_takeover_type')),
        'reject_type': bucket([r for r in annotated if not r.get('v83_quality_gate')], lambda r: r.get('v83_takeover_type')),
        't1_violations': sum(1 for r in selected if str(r.get('entry_date')) == str(r.get('exit_date'))),
        'missing_kline': missing_kline,
        'field_audit': {
            'missing_select_date': sum(1 for r in selected if not r.get('select_date')),
            'missing_join_date': sum(1 for r in selected if not r.get('join_date')),
            'missing_zone': sum(1 for r in selected if not (r.get('zone_low') and r.get('zone_high'))),
            'missing_cost_line': sum(1 for r in selected if not r.get('smart_money_cost')),
            'missing_volatility': sum(1 for r in selected if not r.get('volatility_pct')),
        },
    }
    (OUT / 'v83_annotated_candidates.json').write_text(json.dumps(annotated, ensure_ascii=False))
    (OUT / 'v83_selected_candidates.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v83_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
