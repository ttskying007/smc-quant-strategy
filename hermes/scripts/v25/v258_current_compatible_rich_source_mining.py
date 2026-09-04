#!/usr/bin/env python3
"""V258 no-write: mine rich source-side rules that are compatible with current supply.

Goal: after V255 only tested coarse current-compatible family/risk and failed,
search a wider but still source-side predicate space on the historical V230
universe. A candidate is useful only if it (a) adds non-overlap child supply to
V246/V248, (b) has current recent rows, and (c) keeps combined historical gates.
No production/frontend/watchlist writes.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from itertools import combinations

import pandas as pd

BASE = Path('/root/.hermes')
BASELINE = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
UNIVERSE = BASE / 'smc_audit/v230_v228_plus_new_supply_expansion_probe_no_write_20260627_053747/v230_candidate_pool_enriched.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v258_current_compatible_rich_source_mining_no_write_{TS}'
LATEST = BASE / 'smc_audit/v258_current_compatible_rich_source_mining_latest.json'

PROD = dict(n=570, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=1)
RESEARCH = dict(n=570, min_year_n=70, wr=94.0, avg=7.45, year_wr_min=92.0, micro=1.0, weak_month_count=2)

KEY = ['symbol', 'entry_date']

SAFE_NUMERIC = [
    'risk_pct', 'v85_zone_width_pct', 'reclaim_close_above_zone_pct', 'reclaim_close_pos',
    'touch_to_reclaim_bars', 'entry_chase_above_zone_pct', 'source_gap_atr', 'source_mid_body_atr',
    'v132_reclaim_body_range_pct', 'v132_reclaim_bull_body_pct', 'v132_reclaim_close_pos_pct',
    'v132_reclaim_low_below_zone_high_pct', 'v132_reclaim_close_above_zone_high_pct',
    'v230_all_strong1_pct', 'v230_board_strong1_pct', 'v230_p3_strong1_pct',
]
SAFE_CATEGORICAL = [
    'poi_source', 'combo_family', 'event_type', 'market_state', 'v132_reclaim_class',
    'v132_true_takeover_1', 'v132_true_takeover_2', 'v132_true_takeover_3_strict',
    'v160_rule_pass', 'v164_rule_pass',
]
LEAK_SUBSTRINGS = ['pnl', 'exit', 'won', 'mfe', 'mae', 'same_day', 'tp', 'sl', 'hold_bars', 'r_mult', 'rr_realized']


def norm_date(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace('.0', '', regex=False)


def add_key(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['entry_date'] = norm_date(df['entry_date'])
    df['_key'] = df['symbol'].astype(str) + '|' + df['entry_date'].astype(str)
    return df


def metrics(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {'n': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    years = norm_date(df['entry_date']).str[:4]
    months = norm_date(df['entry_date']).str[:6]
    year_counts = years.value_counts().sort_index().to_dict()
    year_wr = {str(y): round((pnl[years == y] > 0).mean() * 100, 2) for y in sorted(years.dropna().unique())}
    weak = []
    for m, g in df.groupby(months):
        gp = pd.to_numeric(g['pnl_pct'], errors='coerce')
        if len(g) >= 10:
            wr = (gp > 0).mean() * 100
            avg = gp.mean()
            if wr < 90 or avg < 5.5:
                weak.append({'period': str(m), 'n': int(len(g)), 'wr': round(wr, 2), 'avg': round(avg, 4), 'loss': int((gp <= 0).sum())})
    return {
        'n': int(n),
        'wr': round((pnl > 0).mean() * 100, 4),
        'avg': round(pnl.mean(), 4),
        'median': round(pnl.median(), 4),
        'min_year_n': int(min(year_counts.values()) if year_counts else 0),
        'year_counts': {str(k): int(v) for k, v in year_counts.items()},
        'year_wr': year_wr,
        'all_year_wr_min': round(min(year_wr.values()) if year_wr else 0, 2),
        'micro': round(((pnl > 0) & (pnl < 1)).mean() * 100, 4),
        'loss': int((pnl <= 0).sum()),
        'weak_month_count': len(weak),
        'weak_months': weak[:8],
        't1': int(df['t1_violation'].fillna(False).astype(bool).sum()) if 't1_violation' in df else 0,
    }


def pass_gate(m: dict, gate: dict) -> bool:
    return (m.get('n', 0) >= gate['n'] and m.get('min_year_n', 0) >= gate['min_year_n']
            and m.get('wr', 0) >= gate['wr'] and m.get('avg', 0) >= gate['avg']
            and m.get('all_year_wr_min', 0) >= gate['year_wr_min'] and m.get('micro', 99) <= gate['micro']
            and m.get('weak_month_count', 99) <= gate['weak_month_count'] and m.get('t1', 1) == 0)


def pred_mask(df: pd.DataFrame, pred: tuple) -> pd.Series:
    col, op, val = pred
    if op == '==':
        return df[col].astype(str) == str(val)
    x = pd.to_numeric(df[col], errors='coerce')
    if op == '<=':
        return x <= float(val)
    if op == '>=':
        return x >= float(val)
    raise ValueError(pred)


def pred_str(pred: tuple) -> str:
    c, op, v = pred
    if isinstance(v, float):
        return f'{c} {op} {v:.6g}'
    return f'{c} {op} {v}'


def build_predicates(hist_child: pd.DataFrame, current: pd.DataFrame) -> list[tuple]:
    preds = []
    for c in SAFE_CATEGORICAL:
        if c not in hist_child or c not in current:
            continue
        vals = current[c].dropna().astype(str).value_counts().head(8).index.tolist()
        for v in vals:
            # avoid predicates that match almost everything and add no structure
            if (hist_child[c].astype(str) == v).sum() >= 15:
                preds.append((c, '==', v))
    for c in SAFE_NUMERIC:
        if c not in hist_child or c not in current:
            continue
        x = pd.to_numeric(hist_child[c], errors='coerce').dropna()
        cx = pd.to_numeric(current[c], errors='coerce').dropna()
        if len(x) < 100 or len(cx) < 3:
            continue
        qs = sorted(set([0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]))
        for q in qs:
            th = float(x.quantile(q))
            # only keep threshold predicates that have at least one current hit
            for op in ('<=', '>='):
                if (cx <= th).sum() if op == '<=' else (cx >= th).sum():
                    preds.append((c, op, th))
    return preds


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = add_key(pd.read_csv(BASELINE))
    uni = add_key(pd.read_csv(UNIVERSE))
    base_keys = set(base['_key'])
    child_universe = uni[~uni['_key'].isin(base_keys)].copy()
    # Current-compatible: scanner rows from the most recent 45-day dry-run materialization.
    if 'v161_recent45' in child_universe:
        current = child_universe[child_universe['v161_recent45'].fillna(False).astype(bool)].copy()
    else:
        latest = norm_date(child_universe['entry_date']).max()
        current = child_universe[norm_date(child_universe['entry_date']) >= latest].copy()
    # Do not let old duplicate events inflate current compatibility.
    current = current.drop_duplicates('_key')
    preds = build_predicates(child_universe, current)
    leak_fields = [c for c in SAFE_NUMERIC + SAFE_CATEGORICAL if any(s in c.lower() for s in LEAK_SUBSTRINGS)]

    rows = []
    # singles + pairs. Limit pair space by requiring each single has current hits and some historical edge.
    single_stats = []
    for p in preds:
        hm = pred_mask(child_universe, p)
        cm = pred_mask(current, p)
        h = child_universe[hm]
        cur = current[cm]
        if len(h) < 20 or len(cur) < 1:
            continue
        m = metrics(h)
        single_stats.append((p, len(cur), m.get('wr', 0), m.get('avg', 0)))
    single_stats = sorted(single_stats, key=lambda x: (x[1] > 0, x[2], x[3]), reverse=True)[:120]
    candidates = [(p,) for p, *_ in single_stats]
    candidates += [pair for pair in combinations([x[0] for x in single_stats[:80]], 2)]

    seen = set()
    for combo in candidates:
        label = ' AND '.join(pred_str(p) for p in combo)
        if label in seen:
            continue
        seen.add(label)
        hm = pd.Series(True, index=child_universe.index)
        cm = pd.Series(True, index=current.index)
        for p in combo:
            hm &= pred_mask(child_universe, p)
            cm &= pred_mask(current, p)
        child = child_universe[hm].drop_duplicates('_key')
        cur = current[cm].drop_duplicates('_key')
        if len(child) < 15 or len(cur) < 1:
            continue
        combined = pd.concat([base, child], ignore_index=True).drop_duplicates('_key')
        cmx = metrics(combined)
        chm = metrics(child)
        rows.append({
            'rule': label,
            'pred_count': len(combo),
            'current_hits': int(len(cur)),
            'child_n': int(len(child)),
            'child_wr': chm.get('wr'), 'child_avg': chm.get('avg'), 'child_min_year_n': chm.get('min_year_n'),
            'combined_prod_pass': pass_gate(cmx, PROD),
            'combined_research_pass': pass_gate(cmx, RESEARCH),
            **{f'combined_{k}': v for k, v in cmx.items() if k not in ['weak_months','year_counts','year_wr']},
            'combined_year_counts': cmx.get('year_counts'),
            'combined_year_wr': cmx.get('year_wr'),
            'combined_weak_months': cmx.get('weak_months'),
        })
    frontier = pd.DataFrame(rows)
    if not frontier.empty:
        frontier = frontier.sort_values(
            ['combined_prod_pass', 'combined_research_pass', 'current_hits', 'combined_weak_month_count', 'combined_wr', 'combined_avg'],
            ascending=[False, False, False, True, False, False]
        )
    frontier.to_csv(OUT / 'v258_frontier.csv', index=False)
    best_rows_path = None
    if not frontier.empty:
        best_rule = frontier.iloc[0]['rule']
        masks = [tuple(None for _ in range(3))]
        # re-evaluate best rule by parsing from original combos table is cumbersome; save top current rows separately by broad current sample.
        current.to_csv(OUT / 'v258_current_recent45_nonoverlap_rows.csv', index=False)
        best_rows_path = str(OUT / 'v258_current_recent45_nonoverlap_rows.csv')

    summary = {
        'version': 'V258_CURRENT_COMPATIBLE_RICH_SOURCE_MINING_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'sources': {'baseline': str(BASELINE), 'universe': str(UNIVERSE)},
        'baseline_metrics': metrics(base),
        'child_universe_rows': int(len(child_universe)),
        'current_recent45_nonoverlap_rows': int(len(current)),
        'predicate_count': int(len(preds)),
        'rules_tested': int(len(candidates)),
        'frontier_rows': int(len(frontier)),
        'production_pass_count': int(frontier['combined_prod_pass'].sum()) if not frontier.empty else 0,
        'research_pass_count': int(frontier['combined_research_pass'].sum()) if not frontier.empty else 0,
        'top_candidates': frontier.head(20).to_dict('records') if not frontier.empty else [],
        'selector_fields': SAFE_NUMERIC + SAFE_CATEGORICAL,
        'selector_leak_fields': leak_fields,
        'decision': 'PENDING',
        'artifacts': {'frontier': str(OUT / 'v258_frontier.csv'), 'current_rows': best_rows_path, 'summary_json': str(OUT / 'v258_summary.json')},
    }
    if summary['production_pass_count'] > 0:
        summary['decision'] = 'V258_CURRENT_COMPATIBLE_SOURCE_RULE_FOUND__REQUIRES_INDEPENDENT_AUDIT_AND_TRUE_CURRENT_SCANNER_SMOKE_BEFORE_ANY_PROMOTION'
    elif summary['research_pass_count'] > 0:
        summary['decision'] = 'V258_RESEARCH_ONLY_CURRENT_COMPATIBLE_RULE_FOUND__NO_PRODUCTION_WRITE'
    else:
        summary['decision'] = 'V258_NO_CURRENT_COMPATIBLE_RICH_SOURCE_RULE__CURRENT_SSL_DEMAND_SUPPLY_REMAINS_REJECTED'
    (OUT / 'v258_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
