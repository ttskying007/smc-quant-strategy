#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from v81_full_market_scan import f
from v84_smart_money_path_split_gate import evaluate_v84_path_gate

SRC = Path('/root/.hermes/smc_opt_v83_post_reclaim_takeover/v83_selected_candidates.json')
ENV_PATH = Path('/root/.hermes/smc_opt_v74_env_state_machine/v74_env_by_date.json')
KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v84_smart_money_path_split')
OUT.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def normalize_env(row: Dict[str, Any]) -> Dict[str, Any]:
    nr = dict(row)
    nr['market_state'] = row.get('market_state_v74') or row.get('market_state') or row.get('state') or ''
    return nr


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def bar_date(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or '')[:8]


def enrich_path_features(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    nr = dict(row)
    sweep_idx = int(f(row.get('sweep_idx'), -1))
    sweep_level = f(row.get('sweep_level'))
    if 0 <= sweep_idx < len(ks) and sweep_level:
        sweep_low = f(ks[sweep_idx].get('l'))
        nr['sweep_low'] = round(sweep_low, 6)
        nr['sweep_pierce_pct'] = round(max(0.0, (sweep_level / sweep_low - 1) * 100), 4) if sweep_low else 0
    elif row.get('event_type') == 'BOS_CONTINUATION':
        nr['sweep_pierce_pct'] = 0
    else:
        nr['sweep_pierce_pct'] = f(row.get('sweep_pierce_pct'), 0)
    return nr


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
    env_raw = load_json(ENV_PATH)
    env_by_date = {str(k)[:8]: normalize_env(v) for k, v in env_raw.items()}
    kcache: Dict[str, List[Dict[str, Any]]] = {}
    annotated: List[Dict[str, Any]] = []
    selected: List[Dict[str, Any]] = []

    for r in rows:
        sym = str(r.get('symbol'))
        if sym not in kcache:
            p = kline_path(sym)
            kcache[sym] = load_json(p) if p.exists() else []
        nr = enrich_path_features(r, kcache[sym])
        gate = evaluate_v84_path_gate(nr, env_by_date)
        nr.update(gate)
        if nr.get('v84_path_gate'):
            selected.append(nr)
        annotated.append(nr)

    report = {
        'engine': 'V84_SMART_MONEY_PATH_SPLIT',
        'source': str(SRC),
        'rules': {
            'base': 'V83 selected candidates only',
            'continuation': 'UP_CONTINUATION + BOS_CONTINUATION + HOLD_ABOVE_POI + post-takeover market in BULL_CONTINUATION/RECOVERY/ACCUMULATION',
            'reversal': 'SSL_SWEEP_CHOCH + HOLD_ABOVE_POI + sweep_pierce>=0.8% + post-takeover recovery/accumulation/bull continuation; MIXED cannot remain MIXED',
            'downgrade': 'POST_RECLAIM_HIGHER_LOW rejected as weak smart-money control',
        },
        'metrics': {
            'v83_source': metrics(rows),
            'v84_selected': metrics(selected),
        },
        'year': bucket(selected, lambda r: str(r.get('entry_date', ''))[:4]),
        'path': bucket(selected, lambda r: r.get('v84_path')),
        'story': bucket(selected, lambda r: r.get('story')),
        'market_state': bucket(selected, lambda r: r.get('market_state')),
        'post_takeover_market_state': bucket(selected, lambda r: r.get('v84_post_takeover_market_state')),
        'reject_reason': bucket([r for r in annotated if not r.get('v84_path_gate')], lambda r: r.get('v84_reject_reason')),
        'exit_reason': bucket(selected, lambda r: r.get('exit_reason')),
        't1_violations': sum(1 for r in selected if str(r.get('entry_date')) == str(r.get('exit_date'))),
        'field_audit': {
            'missing_select_date': sum(1 for r in selected if not r.get('select_date')),
            'missing_join_date': sum(1 for r in selected if not r.get('join_date')),
            'missing_zone': sum(1 for r in selected if not (r.get('zone_low') and r.get('zone_high'))),
            'missing_cost_line': sum(1 for r in selected if not r.get('smart_money_cost')),
            'missing_volatility': sum(1 for r in selected if not r.get('volatility_pct')),
        },
    }
    (OUT / 'v84_annotated_candidates.json').write_text(json.dumps(annotated, ensure_ascii=False))
    (OUT / 'v84_selected_candidates.json').write_text(json.dumps(selected, ensure_ascii=False))
    (OUT / 'v84_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
