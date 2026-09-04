#!/usr/bin/env python3
"""V365 no-write chronological closure of the V333 daily-rule search.

Tests whether any V333 source-safe daily predicate conjunction survives selection
on earlier years and a fixed out-of-sample gate. It never writes production,
watchlist, frontend, or live files.
"""
from __future__ import annotations

import itertools
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V333 = AUD / 'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
OUT = AUD / f'v365_v333_rule_walkforward_closure_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v365_v333_rule_walkforward_closure_latest.json'

# These thresholds are set before inspection. Discovery requires adequate two-year
# development coverage; promotion requires it again on unseen years.
DEV_GATE = dict(n=120, min_year_n=40, wr=90.0, avg=7.0, min_year_wr=88.0, micro=1.0, t1=0)
OOS_GATE = dict(n=100, min_year_n=40, wr=90.0, avg=7.0, min_year_wr=88.0, micro=1.0, t1=0)
OOS_2026_GATE = dict(n=40, min_year_n=40, wr=90.0, avg=7.0, min_year_wr=88.0, micro=1.0, t1=0)
WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}


def boolish(x: object) -> bool:
    return str(x).strip().lower() in {'true', '1', 'yes'}


def metric(df: pd.DataFrame) -> dict:
    closed = df[df['replay_status'].astype(str).eq('CLOSED')].copy()
    if closed.empty:
        return dict(n=0, wr=0.0, avg=0.0, min_year_n=0, min_year_wr=0.0, micro=0.0, t1=0, year_counts={}, year_wr={})
    pnl = pd.to_numeric(closed['pnl_pct'], errors='coerce')
    years = closed['entry_date'].astype(str).str[:4]
    counts = years.value_counts().sort_index()
    year_wr = {str(y): round(float((pnl[years == y] > 0).mean() * 100), 4) for y in counts.index}
    return dict(
        n=int(len(closed)), wr=round(float((pnl > 0).mean() * 100), 4), avg=round(float(pnl.mean()), 4),
        min_year_n=int(counts.min()), min_year_wr=round(float(min(year_wr.values())), 4),
        micro=round(float(((pnl > 0) & (pnl < 1)).mean() * 100), 4),
        t1=int(closed['same_day_exit_violation'].astype(str).str.lower().isin({'true', '1'}).sum()),
        year_counts={str(k): int(v) for k, v in counts.items()}, year_wr=year_wr,
    )


def passes(m: dict, gate: dict) -> bool:
    return (m['n'] >= gate['n'] and m['min_year_n'] >= gate['min_year_n'] and
            m['wr'] >= gate['wr'] and m['avg'] >= gate['avg'] and
            m['min_year_wr'] >= gate['min_year_wr'] and m['micro'] <= gate['micro'] and m['t1'] == gate['t1'])


def predicates(df: pd.DataFrame) -> dict[str, pd.Series]:
    n = lambda col: pd.to_numeric(df.get(col, pd.Series(index=df.index)), errors='coerce')
    b = lambda col: df.get(col, pd.Series(False, index=df.index)).map(boolish)
    weak = df['v244_industry'].astype(str).isin(WEAK_INDUSTRIES)
    industry = (~weak) | n('v244_ind_strong1_pct').ge(31.1688) | n('v236_br_above_ma20').ge(46.8561)
    return {
        'v164': b('v164_rule_pass'), 'industry': industry,
        'tt3': b('v132_true_takeover_3_strict'),
        'tt2_or_tt3': b('v132_true_takeover_2') | b('v132_true_takeover_3_strict'),
        'tt2_only': b('v132_true_takeover_2') & ~b('v132_true_takeover_3_strict'),
        'bull3_ge3': n('v132_bull_count_3').ge(3), 'bull3_ge2': n('v132_bull_count_3').ge(2),
        'body_le60': n('v132_reclaim_bull_body_pct').le(60), 'body_le75': n('v132_reclaim_bull_body_pct').le(75),
        'chase_le2': n('entry_chase_above_zone_pct').le(2), 'chase_le3': n('entry_chase_above_zone_pct').le(3),
        'risk_2_6': n('risk_pct').between(2, 6, inclusive='both'), 'risk_le5': n('risk_pct').le(5),
        'zone_ge2': n('v85_zone_width_pct').ge(2), 'pull3_le2': n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(2),
        'pull3_le0': n('v132_post_zone_pullback_depth_pct_3').fillna(999).le(.0001),
        'bear_risk': df.get('market_state', pd.Series('', index=df.index)).astype(str).eq('BEAR_RISK'),
        'recovery_or_bear': df.get('market_state', pd.Series('', index=df.index)).astype(str).isin({'RECOVERY', 'BEAR_RISK'}),
        'demand_ob': df.get('poi_source', pd.Series('', index=df.index)).astype(str).eq('DEMAND_OB'),
        'ob_or_obfvg': df.get('poi_source', pd.Series('', index=df.index)).astype(str).isin({'DEMAND_OB', 'OB+FVG'}),
        'ssl_reversal': df.get('event_type', pd.Series('', index=df.index)).astype(str).eq('SSL_SWEEP_CHOCH_REVERSAL'),
        'strong1_le25': n('v236_all_strong1_pct').le(25), 'strong1_5_35': n('v236_all_strong1_pct').between(5, 35, inclusive='both'),
        'br_20_55': n('v236_br_above_ma20').between(20, 55, inclusive='both'), 'br_25_45': n('v236_br_above_ma20').between(25, 45, inclusive='both'),
        'ind_strong_ge10': n('v244_ind_strong1_pct').ge(10), 'ind_up_le80': n('v244_ind_up1_pct').le(80),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(V333.read_text())
    df = pd.read_csv(report['artifacts']['replayed_csv'], low_memory=False)
    years = df['entry_date'].astype(str).str[:4]
    hist = df[df['v333_actual_bars_since_entry'].ge(10)].copy()
    p = predicates(hist)
    base = ['v164', 'industry']
    extra = [x for x in p if x not in base]
    rules: list[tuple[str, pd.Series]] = []
    for width in range(4):
        for suffix in itertools.combinations(extra, width):
            names = base + list(suffix)
            mask = pd.Series(True, index=hist.index)
            for name in names:
                mask &= p[name].fillna(False)
            rules.append((' & '.join(names), mask))

    folds = [
        ('WF_A_2023_2024_TO_2025_2026', {'2023', '2024'}, {'2025', '2026'}, DEV_GATE, OOS_GATE),
        ('WF_B_2023_2025_TO_2026', {'2023', '2024', '2025'}, {'2026'}, DEV_GATE, OOS_2026_GATE),
    ]
    fold_results = []
    survivors = None
    for label, train_years, test_years, dev_gate, oos_gate in folds:
        train_mask, test_mask = years.loc[hist.index].isin(train_years), years.loc[hist.index].isin(test_years)
        selected = []
        for rule, mask in rules:
            dev = metric(hist[mask & train_mask])
            if passes(dev, dev_gate):
                test = metric(hist[mask & test_mask])
                selected.append(dict(rule=rule, dev=dev, test=test, oos_pass=passes(test, oos_gate)))
        selected.sort(key=lambda r: (r['oos_pass'], r['test']['min_year_wr'], r['test']['wr'], r['test']['avg'], r['test']['n']), reverse=True)
        names = {x['rule'] for x in selected if x['oos_pass']}
        survivors = names if survivors is None else survivors & names
        fold_results.append(dict(label=label, train_years=sorted(train_years), test_years=sorted(test_years), development_gate=dev_gate, oos_gate=oos_gate, development_selected_count=len(selected), oos_pass_count=len(names), best_oos_results=selected[:20]))

    result = {
        'version': 'V365_V333_RULE_WALKFORWARD_CLOSURE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': report['artifacts']['replayed_csv'],
        'contract': 'exact V333 source-time predicate universe; rule selection happens only in prior years; all replay exits remain T+1 from V333',
        'rows_historical': int(len(hist)), 'rule_count': len(rules), 'folds': fold_results,
        'common_oos_survivors': sorted(survivors or []),
        'decision': 'CLOSE_V333_DAILY_CONJUNCTION_ROUTE__NO_RULE_SURVIVES_BOTH_PREDECLARED_OOS_GATES' if not survivors else 'RESEARCH_CANDIDATE_ONLY__REQUIRES_INDEPENDENT_SEMANTIC_REDERIVATION',
        'next_direction': 'Do not add daily scalar conjunctions. Acquire full 2023-2026 intraday history, then test an intraday POI reaction generator with the same T+1 and walk-forward gates.'
    }
    (OUT / 'v365_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
