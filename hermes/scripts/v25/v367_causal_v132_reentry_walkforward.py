#!/usr/bin/env python3
"""V367 no-write causal rebuild of the V365 daily candidate route.

The V365 survivor entered before its V132 takeover confirmation.  This script
replays every V164-eligible row only at the first open after its actually
observed takeover confirmation (strict-3 if present, else takeover-2), then
re-runs the same predeclared V365 walk-forward gates.

No production, frontend, watchlist, or live-state writes.
"""
from __future__ import annotations

import csv
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
V333 = AUD / 'v333_full_universe_rule_search_after_breadth_refresh_latest.json'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v367_causal_v132_reentry_walkforward_no_write_{STAMP}'
LATEST = AUD / 'v367_causal_v132_reentry_walkforward_latest.json'

# Fixed before the rebuild: unchanged from V365/V316 closure.
DEV_GATE = dict(n=120, min_year_n=40, wr=90.0, avg=7.0, min_year_wr=88.0, micro=1.0, t1=0)
OOS_GATE = dict(n=100, min_year_n=40, wr=90.0, avg=7.0, min_year_wr=88.0, micro=1.0, t1=0)
OOS_2026_GATE = dict(n=40, min_year_n=40, wr=90.0, avg=7.0, min_year_wr=88.0, micro=1.0, t1=0)
WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}

sys.path.insert(0, str(ROOT / 'scripts/v25'))
from v132_fvg_reclaim_takeover_shadow_backtest import load_json, simulate_delayed_entry  # noqa: E402


def boolish(x: object) -> bool:
    return str(x).strip().lower() in {'true', '1', 'yes'}


def kline(symbol: str, cache: dict[str, list[dict]]) -> list[dict]:
    if symbol not in cache:
        path = KDIR / f'{symbol.replace(".", "_")}_daily_750.json'
        cache[symbol] = load_json(path) if path.exists() else []
    return cache[symbol]


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
    source = pd.read_csv(report['artifacts']['replayed_csv'], low_memory=False)
    source = source[source['v333_actual_bars_since_entry'].ge(10)].copy()
    source = source[source['v164_rule_pass'].map(boolish)].copy()

    cache: dict[str, list[dict]] = {}
    rows: list[dict] = []
    statuses: dict[str, int] = {}
    causality_failures = 0
    for row in source.to_dict('records'):
        strict3 = boolish(row.get('v132_true_takeover_3_strict'))
        n = 3 if strict3 else 2
        confirm_idx = int(float(row.get(f'v132_entry_after_confirm_idx_{n}', -1)))
        original_entry = int(float(row.get('entry_idx', -1)))
        if confirm_idx <= original_entry:
            causality_failures += 1
            continue
        replay = simulate_delayed_entry(row, kline(str(row['symbol']), cache), n, f'V367_CAUSAL_TAKEOVER_{n}')
        if replay is None:
            statuses['UNREPLAYABLE'] = statuses.get('UNREPLAYABLE', 0) + 1
            continue
        status = 'CLOSED' if replay.get('v132_delayed_exit_date') else 'OPEN_RIGHT_EDGE'
        statuses[status] = statuses.get(status, 0) + 1
        merged = dict(row)
        merged.update(replay)
        merged.update({
            'replay_status': status,
            'entry_idx': replay.get('v132_delayed_entry_idx'),
            'entry_date': str(replay.get('v132_delayed_entry_date', '')),
            'entry_price': replay.get('v132_delayed_entry_price'),
            'exit_date': str(replay.get('v132_delayed_exit_date', '')),
            'exit_price': replay.get('v132_delayed_exit_price'),
            'exit_reason': replay.get('v132_delayed_exit_reason'),
            'hold_bars': replay.get('v132_delayed_hold_bars'),
            'pnl_pct': replay.get('v132_delayed_pnl_pct'),
            'same_day_exit_violation': str(replay.get('v132_delayed_entry_date', '')) == str(replay.get('v132_delayed_exit_date', '')),
            'v367_confirmation_n': n,
            'v367_original_entry_idx': original_entry,
            'v367_confirmation_entry_idx': confirm_idx,
            'v367_entry_after_confirmation': int(replay.get('v132_delayed_entry_idx', -1)) >= confirm_idx,
        })
        rows.append(merged)

    df = pd.DataFrame(rows)
    row_path = OUT / 'v367_causal_replayed.csv'
    df.to_csv(row_path, index=False)
    closed = df[df['replay_status'].eq('CLOSED')].copy()
    p = predicates(closed)
    base = ['v164', 'industry']
    extra = [x for x in p if x not in base]
    rules: list[tuple[str, pd.Series]] = []
    for width in range(4):
        for suffix in itertools.combinations(extra, width):
            names = base + list(suffix)
            mask = pd.Series(True, index=closed.index)
            for name in names:
                mask &= p[name].fillna(False)
            rules.append((' & '.join(names), mask))

    years = closed['entry_date'].astype(str).str[:4]
    folds = [
        ('WF_A_2023_2024_TO_2025_2026', {'2023', '2024'}, {'2025', '2026'}, DEV_GATE, OOS_GATE),
        ('WF_B_2023_2025_TO_2026', {'2023', '2024', '2025'}, {'2026'}, DEV_GATE, OOS_2026_GATE),
    ]
    fold_results, survivors = [], None
    for label, train_years, test_years, dev_gate, oos_gate in folds:
        train, test = years.isin(train_years), years.isin(test_years)
        selected = []
        for rule, mask in rules:
            dev = metric(closed[mask & train])
            if passes(dev, dev_gate):
                oos = metric(closed[mask & test])
                selected.append(dict(rule=rule, dev=dev, test=oos, oos_pass=passes(oos, oos_gate)))
        selected.sort(key=lambda x: (x['oos_pass'], x['test']['min_year_wr'], x['test']['wr'], x['test']['avg'], x['test']['n']), reverse=True)
        names = {x['rule'] for x in selected if x['oos_pass']}
        survivors = names if survivors is None else survivors & names
        fold_results.append(dict(label=label, train_years=sorted(train_years), test_years=sorted(test_years), development_selected_count=len(selected), oos_pass_count=len(names), best_oos_results=selected[:20]))

    result = {
        'version': 'V367_CAUSAL_V132_REENTRY_WALKFORWARD_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V333 historical V164 rows; true takeover-3 enters at reclaim+4 open, otherwise true takeover-2 enters at reclaim+3 open',
        'exit_contract': 'V132 semantic exit from delayed-entry horizon; first semantic exit is T+1; no entry-day exit',
        'fixed_gates': {'development': DEV_GATE, 'oos_2025_2026': OOS_GATE, 'oos_2026': OOS_2026_GATE},
        'source_rows_v164': int(len(source)), 'replay_status_counts': statuses,
        'causality': {'entry_before_required_confirmation': causality_failures, 'all_replayed_entries_at_or_after_confirmation': bool(df['v367_entry_after_confirmation'].all()) if len(df) else False, 'same_day_exit_violations': int(df['same_day_exit_violation'].sum()) if len(df) else 0},
        'all_causal_replay_metrics': metric(closed), 'rule_count': len(rules), 'folds': fold_results,
        'common_oos_survivors': sorted(survivors or []),
        'decision': 'RESEARCH_ONLY_SURVIVOR__REQUIRES_INDEPENDENT_SEMANTIC_AUDIT' if survivors else 'CLOSE_V365_ROUTE_AFTER_CAUSAL_REENTRY__NO_RULE_SURVIVES_FIXED_WALKFORWARD_GATES',
        'artifacts': {'out_dir': str(OUT), 'replayed_csv': str(row_path), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v367_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
