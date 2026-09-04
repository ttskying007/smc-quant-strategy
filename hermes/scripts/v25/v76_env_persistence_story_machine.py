#!/usr/bin/env python3
"""V76 environment persistence + story gate audit.

V75 proved the largest residual loss bucket is POI close-break after entry. This
script does not tune TP/SL first. It adds the missing higher-level state checks:
- environment persistence before entry (avoid one-day false bull after distribution)
- story-specific gate (continuation and reversal need different environments)
- BSL target distance as a liquidity objective sanity check
- explicit post-entry invalidation labels for the surviving set
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

V75_DIR = Path('/root/.hermes/smc_opt_v75_post_entry_invalidation')
V74_DIR = Path('/root/.hermes/smc_opt_v74_env_state_machine')
OUT_DIR = Path('/root/.hermes/smc_opt_v76_env_persistence_story_machine')
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEMAND_ENV = {'ACCUMULATION', 'RECOVERY', 'BULL_CONTINUATION'}
RISK_ENV = {'DISTRIBUTION', 'BEAR_RISK'}


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        return float(x)
    except Exception:
        return default


def date_key(t: Dict[str, Any]) -> str:
    return str(t.get('entry_date') or t.get('pick_date') or t.get('select_date') or '')[:8]


def metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    if not rows:
        return {'n': 0, 'wr': 0, 'sl_rate': 0, 'avg_pnl': 0, 'cum': 0, 'avg_win': 0, 'avg_loss': 0, 'payoff': 0, 'poi_break_rate': 0}
    wins = [r for r in rows if f(r.get('pnl_pct')) > 0]
    losses = [r for r in rows if f(r.get('pnl_pct')) <= 0]
    sl = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    poi_break = [r for r in rows if r.get('v75_primary_post_entry_fail') == 'LOSS_POI_CLOSE_BREAK_BEFORE_TP']
    aw = sum(f(r.get('pnl_pct')) for r in wins) / len(wins) if wins else 0
    al = sum(f(r.get('pnl_pct')) for r in losses) / len(losses) if losses else 0
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'sl_rate': round(len(sl) / len(rows) * 100, 2),
        'avg_pnl': round(sum(f(r.get('pnl_pct')) for r in rows) / len(rows), 4),
        'cum': round(sum(f(r.get('pnl_pct')) for r in rows), 2),
        'avg_win': round(aw, 4),
        'avg_loss': round(al, 4),
        'payoff': round(aw / abs(al), 3) if al else 0,
        'poi_break_rate': round(len(poi_break) / len(rows) * 100, 2),
    }


def bucket(rows: Iterable[Dict[str, Any]], key: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def env_window(env: Dict[str, Dict[str, Any]], dates: List[str], dt: str, n: int) -> List[str]:
    if dt not in env:
        return []
    i = dates.index(dt)
    prior = dates[max(0, i - n):i]
    return [str(env[d].get('market_state_v74') or env[d].get('state') or 'MIXED') for d in prior]


def annotate(rows: List[Dict[str, Any]], env: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    dates = sorted(env)
    out: List[Dict[str, Any]] = []
    for r in rows:
        nr = dict(r)
        dt = date_key(nr)
        p5 = env_window(env, dates, dt, 5)
        p10 = env_window(env, dates, dt, 10)
        nr['v76_prior5_env_states'] = p5
        nr['v76_prior10_env_states'] = p10
        nr['v76_prior5_distribution_days'] = sum(1 for x in p5 if x in RISK_ENV)
        nr['v76_prior10_distribution_days'] = sum(1 for x in p10 if x in RISK_ENV)
        nr['v76_prior5_demand_valid_days'] = sum(1 for x in p5 if x in DEMAND_ENV)
        nr['v76_prior10_demand_valid_days'] = sum(1 for x in p10 if x in DEMAND_ENV)
        nr['v76_env_persistent'] = nr['v76_prior5_distribution_days'] == 0 and nr['v76_prior5_demand_valid_days'] >= 2
        story = str(nr.get('setup_story_v74') or '')
        env_state = str(nr.get('market_state_v74') or '')
        breadth = f(nr.get('market_bull_breadth'))
        bsl_dist = f(nr.get('bsl_distance_pct'), 999)
        # Continuation is only valid in a persistent bull continuation environment.
        if story == 'UP_CONTINUATION_BOS_POI_RECLAIM':
            nr['v76_story_env_match'] = env_state == 'BULL_CONTINUATION' and nr['v76_env_persistent']
        # Reversal/recovery setups are valid in recovery/accumulation, but not if
        # they are immediately following distribution/bear risk.
        elif story in {'DOWN_REVERSAL_SSL_CHOCH_POI_RECLAIM', 'BULL_TRANSITION_POI_RECLAIM'}:
            nr['v76_story_env_match'] = env_state in {'RECOVERY', 'ACCUMULATION'} and nr['v76_prior5_distribution_days'] == 0
        else:
            nr['v76_story_env_match'] = False
        nr['v76_bsl_target_sane'] = bool(nr.get('bsl_available')) and 0.25 <= bsl_dist <= 6.0
        nr['v76_breadth_not_overheated'] = breadth <= 0.55
        nr['v76_gate'] = bool(nr.get('v74_core_gate')) and nr['v76_story_env_match'] and nr['v76_bsl_target_sane'] and nr['v76_breadth_not_overheated']
        reasons = []
        for flag, label in [
            ('v74_core_gate', 'FAIL_V74_CORE'),
            ('v76_story_env_match', 'FAIL_STORY_ENV'),
            ('v76_bsl_target_sane', 'FAIL_BSL_TARGET'),
            ('v76_breadth_not_overheated', 'FAIL_OVERHEATED_BREADTH'),
        ]:
            if not nr.get(flag):
                reasons.append(label)
        nr['v76_reject_reason'] = '+'.join(reasons) if reasons else 'PASS'
        out.append(nr)
    return out


def gate_search(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates = []
    for prior_days in [3, 5, 10]:
        for max_dist_days in [0, 1]:
            for min_demand_days in [1, 2, 3]:
                for max_bsl in [2.0, 3.0, 4.0, 6.0, 999.0]:
                    for max_breadth in [0.45, 0.50, 0.55, 0.65, 999.0]:
                        sel = []
                        for r in rows:
                            p = r.get(f'v76_prior{prior_days}_env_states')
                            if p is None:
                                # derive from 5/10 only for supported cases
                                p = r['v76_prior5_env_states'] if prior_days == 3 else r['v76_prior10_env_states']
                                if prior_days == 3:
                                    p = p[-3:]
                            dist_days = sum(1 for x in p if x in RISK_ENV)
                            demand_days = sum(1 for x in p if x in DEMAND_ENV)
                            if not r.get('v74_core_gate'):
                                continue
                            if dist_days > max_dist_days or demand_days < min_demand_days:
                                continue
                            if not bool(r.get('bsl_available')) or f(r.get('bsl_distance_pct'), 999) > max_bsl:
                                continue
                            if f(r.get('market_bull_breadth')) > max_breadth:
                                continue
                            sel.append(r)
                        m = metrics(sel)
                        if m['n'] >= 80:
                            candidates.append({
                                'prior_days': prior_days, 'max_distribution_days': max_dist_days,
                                'min_demand_days': min_demand_days, 'max_bsl_distance_pct': max_bsl,
                                'max_bull_breadth': max_breadth, **m,
                                'year': bucket(sel, lambda x: date_key(x)[:4]),
                                'story': bucket(sel, lambda x: x.get('setup_story_v74')),
                            })
    candidates.sort(key=lambda x: (x['wr'], x['avg_pnl'], x['n']), reverse=True)
    return candidates[:30]


def main() -> None:
    rows = json.loads((V75_DIR / 'v75_annotated_trades.json').read_text())
    env = json.loads((V74_DIR / 'v74_env_by_date.json').read_text())
    annotated = annotate(rows, env)
    selected = [r for r in annotated if r.get('v76_gate')]
    search = gate_search(annotated)
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': 'V76_ENV_PERSISTENCE_STORY_MACHINE_AUDIT',
        'hypothesis': 'Demand POI works only when context/story/environment persistence and nearby BSL objective agree.',
        'base_v74_selected': metrics(annotated),
        'v76_strict_gate': metrics(selected),
        'buckets': {
            'year': bucket(selected, lambda r: date_key(r)[:4]),
            'market_state': bucket(selected, lambda r: r.get('market_state_v74')),
            'story': bucket(selected, lambda r: r.get('setup_story_v74')),
            'post_entry_fail': bucket(selected, lambda r: r.get('v75_primary_post_entry_fail')),
            'reject_reason': bucket(annotated, lambda r: r.get('v76_reject_reason')),
        },
        'top_gate_search': search,
        'production_readiness': {
            'min_required_n': 500,
            'min_required_each_year_n': 50,
            'min_required_each_year_wr': 65.0,
            'passes': bool(metrics(selected)['n'] >= 500 and all(v['n'] >= 50 and v['wr'] >= 65 for v in bucket(selected, lambda r: date_key(r)[:4]).values())),
        },
        'files': {
            'annotated': str(OUT_DIR / 'v76_annotated_trades.json'),
            'selected': str(OUT_DIR / 'v76_selected_trades.json'),
            'report': str(OUT_DIR / 'v76_report.json'),
        },
    }
    (OUT_DIR / 'v76_annotated_trades.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v76_selected_trades.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v76_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ['base_v74_selected', 'v76_strict_gate', 'buckets', 'production_readiness', 'top_gate_search', 'files']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
