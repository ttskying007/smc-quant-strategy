#!/usr/bin/env python3
"""V77 recovery-quality gate search.

V76 found that RECOVERY is an overloaded state. This script keeps the layered
SMC story model but splits reversal permission:
- continuation: BULL_CONTINUATION + BOS pullback remains primary;
- reversal: RECOVERY is rejected unless it has real accumulation-quality context;
- ACCUMULATION reversal can be tested separately.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

SRC = Path('/root/.hermes/smc_opt_v76_env_persistence_story_machine/v76_annotated_trades.json')
OUT = Path('/root/.hermes/smc_opt_v77_recovery_quality_gate')
OUT.mkdir(parents=True, exist_ok=True)
DEMAND = {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'}
RISK = {'DISTRIBUTION', 'BEAR_RISK'}


def f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x if x not in (None, '') else d)
    except Exception:
        return d


def y(r: Dict[str, Any]) -> str:
    return str(r.get('entry_date') or '')[:4]


def m(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    if not rows:
        return {'n': 0, 'wr': 0, 'avg': 0, 'sl': 0, 'poi_break': 0}
    wins = [r for r in rows if f(r.get('pnl_pct')) > 0]
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'avg': round(sum(f(r.get('pnl_pct')) for r in rows) / len(rows), 4),
        'sl': round(sum(r.get('exit_reason') == 'SL_HIT' for r in rows) / len(rows) * 100, 2),
        'poi_break': round(sum(r.get('v75_primary_post_entry_fail') == 'LOSS_POI_CLOSE_BREAK_BEFORE_TP' for r in rows) / len(rows) * 100, 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    d: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        d[str(key(r))].append(r)
    return {k: m(v) for k, v in sorted(d.items())}


def prior(rows: Dict[str, Any], n: int) -> List[str]:
    p = rows.get('v76_prior10_env_states') or rows.get('v76_prior5_env_states') or []
    return list(p)[-n:]


def pass_candidate(r: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    if not r.get('v74_core_gate'):
        return False
    bsl = f(r.get('bsl_distance_pct'), 999)
    if not bool(r.get('bsl_available')) or bsl > cfg['max_bsl']:
        return False
    if f(r.get('risk_pct'), 999) > cfg['max_risk']:
        return False
    p = prior(r, cfg['prior_days'])
    if sum(1 for x in p if x in RISK) > cfg['max_risk_env_days']:
        return False
    if sum(1 for x in p if x in DEMAND) < cfg['min_demand_days']:
        return False
    story = r.get('setup_story_v74')
    env = r.get('market_state_v74')
    if story == 'UP_CONTINUATION_BOS_POI_RECLAIM':
        return env == 'BULL_CONTINUATION' and f(r.get('market_bull_breadth')) <= cfg['max_cont_breadth']
    # Reversal is the dangerous family: forbid raw RECOVERY unless it has
    # accumulation-quality prior context.
    if story in {'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM', 'BULL_TRANSITION_POI_RECLAIM'}:
        if not cfg['allow_reversal']:
            return False
        if env == 'ACCUMULATION':
            return cfg['allow_accum_reversal']
        if env == 'RECOVERY':
            return (
                cfg['allow_recovery_reversal']
                and p.count('ACCUMULATION') >= cfg['min_prior_accum_for_recovery']
                and f(r.get('market_bull_breadth')) <= cfg['max_recovery_breadth']
                and f(r.get('market_bear_breadth')) <= cfg['max_recovery_bear']
            )
    return False


def main() -> None:
    rows = json.loads(SRC.read_text())
    cfgs = []
    for prior_days in [3, 5, 10]:
        for min_demand_days in [1, 2, 3]:
            for max_bsl in [1.5, 2.0, 3.0, 4.0, 6.0]:
                for max_risk in [4.5, 5.5, 6.5]:
                    for allow_recovery in [False, True]:
                        for min_accum in [1, 2, 3]:
                            cfgs.append({
                                'prior_days': prior_days,
                                'min_demand_days': min_demand_days,
                                'max_risk_env_days': 0,
                                'max_bsl': max_bsl,
                                'max_risk': max_risk,
                                'max_cont_breadth': 0.60,
                                'allow_reversal': True,
                                'allow_accum_reversal': True,
                                'allow_recovery_reversal': allow_recovery,
                                'min_prior_accum_for_recovery': min_accum,
                                'max_recovery_breadth': 0.42,
                                'max_recovery_bear': 0.40,
                            })
    results = []
    for cfg in cfgs:
        sel = [r for r in rows if pass_candidate(r, cfg)]
        mm = m(sel)
        if mm['n'] < 50:
            continue
        years = bucket(sel, y)
        min_year_wr = min((v['wr'] for v in years.values() if v['n'] >= 10), default=0)
        coverage_years = sum(1 for v in years.values() if v['n'] >= 10)
        results.append({**cfg, **mm, 'coverage_years_ge10': coverage_years, 'min_year_wr_ge10': min_year_wr, 'year': years, 'story': bucket(sel, lambda r: r.get('setup_story_v74')), 'market_state': bucket(sel, lambda r: r.get('market_state_v74'))})
    results.sort(key=lambda x: (x['coverage_years_ge10'], x['min_year_wr_ge10'], x['wr'], x['avg'], x['n']), reverse=True)
    best = results[:40]
    selected = [r for r in rows if best and pass_candidate(r, best[0])]
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V77_RECOVERY_QUALITY_GATE_SEARCH',
        'base_v76_annotated': m(rows),
        'best_config': best[0] if best else None,
        'best_selected': m(selected),
        'top_results': best,
        'production_readiness': {
            'passes': bool(best and best[0]['n'] >= 500 and best[0]['coverage_years_ge10'] >= 4 and best[0]['min_year_wr_ge10'] >= 65),
            'reason': 'requires >=500 trades and all 4 years with >=10 trades and >=65% WR',
        },
    }
    (OUT / 'v77_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUT / 'v77_selected_trades.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    print(json.dumps({'best_selected': report['best_selected'], 'best_config': report['best_config'], 'production_readiness': report['production_readiness'], 'files': {'report': str(OUT/'v77_report.json'), 'selected': str(OUT/'v77_selected_trades.json')}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
