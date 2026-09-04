#!/usr/bin/env python3
"""V259 no-write: source-safe BOS_CONTINUATION semantic rebuild.

After V258 exhausted current-compatible scalar mining, test the next valid
source-layer direction: reinterpret BOS_CONTINUATION using only data known before
entry.  No production/frontend/watchlist writes.

Selector safety contract:
- Uses V248/V246 independent selected rows as the historical baseline.
- Adds only non-overlap V230 child rows.
- Raw K-line features use event bar and bars strictly before entry day; entry-day
  high/low/close are not used.
- entry_price/open gap vs pre-entry close is allowed because it is known at fill.
"""
from __future__ import annotations

import json
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
BASELINE = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
UNIVERSE = BASE / 'smc_audit/v230_v228_plus_new_supply_expansion_probe_no_write_20260627_053747/v230_candidate_pool_enriched.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v259_bos_continuation_source_safe_rebuild_no_write_{TS}'
LATEST = BASE / 'smc_audit/v259_bos_continuation_source_safe_rebuild_latest.json'

PROD = dict(n=600, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=6, t1=0)
RESEARCH = dict(n=590, min_year_n=70, wr=93.5, avg=7.5, year_wr_min=91.0, micro=1.0, weak_month_count=8, t1=0)

LEAK_FIELDS_FORBIDDEN = ['pnl', 'exit', 'won', 'mfe', 'mae', 'hold_bars', 'same_day', 'tp', 'sl', 'rr_realized']
RAW_FEATURES = [
    'raw_event_break20_pct',
    'raw_event_close_pos',
    'raw_event_body_pct',
    'raw_event_volr',
    'raw_prev20_range_pct',
    'raw_prev10_range_pct',
    'raw_preentry_min_pullback_pct',
    'raw_preentry_max_push_pct',
    'raw_preentry_last_close_vs_event_pct',
    'raw_entry_gap_vs_preclose_pct',
]
SAFE_SOURCE_FIELDS = RAW_FEATURES + [
    'risk_pct',
    'entry_chase_above_zone_pct',
    'v132_reclaim_body_range_pct',
    'v132_reclaim_close_pos_pct',
    'v132_post_zone_pullback_depth_pct_3',
    'v230_all_strong1_pct',
    'v230_board_strong1_pct',
    'poi_source',
    'market_state',
    'v132_reclaim_class',
]


def norm_date(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace('.0', '', regex=False)


def add_key(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['entry_date_s'] = norm_date(df['entry_date'])
    df['_key'] = df['symbol'].astype(str) + '|' + df['entry_date_s']
    return df


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    years = df['entry_date_s'].astype(str).str[:4]
    months = df['entry_date_s'].astype(str).str[:6]
    year_counts = years.value_counts().sort_index().to_dict()
    year_wr = {str(y): round((pnl[years == y] > 0).mean() * 100, 2) for y in sorted(years.dropna().unique())}
    weak_months = []
    for month, g in df.groupby(months):
        gp = pd.to_numeric(g['pnl_pct'], errors='coerce')
        if len(g) >= 10:
            wr = (gp > 0).mean() * 100
            avg = gp.mean()
            if wr < 90 or avg < 5.5:
                weak_months.append({'period': str(month), 'n': int(len(g)), 'wr': round(wr, 2), 'avg': round(avg, 4), 'loss': int((gp <= 0).sum())})
    return {
        'n': int(len(df)),
        'wr': round((pnl > 0).mean() * 100, 4),
        'avg': round(pnl.mean(), 4),
        'median': round(pnl.median(), 4),
        'min_year_n': int(min(year_counts.values()) if year_counts else 0),
        'year_counts': {str(k): int(v) for k, v in year_counts.items()},
        'year_wr': year_wr,
        'all_year_wr_min': round(min(year_wr.values()) if year_wr else 0, 2),
        'micro': round(((pnl > 0) & (pnl < 1)).mean() * 100, 4),
        'loss': int((pnl <= 0).sum()),
        'weak_month_count': len(weak_months),
        'weak_months': weak_months[:12],
        't1': int(df['t1_violation'].fillna(False).astype(bool).sum()) if 't1_violation' in df else 0,
    }


def pass_gate(m: dict[str, Any], gate: dict[str, float]) -> bool:
    return (
        m.get('n', 0) >= gate['n']
        and m.get('min_year_n', 0) >= gate['min_year_n']
        and m.get('wr', 0) >= gate['wr']
        and m.get('avg', 0) >= gate['avg']
        and m.get('all_year_wr_min', 0) >= gate['year_wr_min']
        and m.get('micro', 99) <= gate['micro']
        and m.get('weak_month_count', 99) <= gate['weak_month_count']
        and m.get('t1', 1) == gate['t1']
    )


def kline_path(symbol: str) -> Path:
    return BASE / 'kline_cache' / f"{symbol.replace('.', '_')}_daily_750.json"


def index_by_date(rows: list[dict[str, Any]], date_s: str) -> int | None:
    for i, bar in enumerate(rows):
        if str(bar.get('t', bar.get('date', ''))) == date_s:
            return i
    return None


def raw_features(row: pd.Series, cache: dict[str, list[dict[str, Any]] | None]) -> dict[str, Any] | None:
    symbol = str(row['symbol'])
    if symbol not in cache:
        path = kline_path(symbol)
        if not path.exists():
            cache[symbol] = None
        else:
            try:
                cache[symbol] = json.loads(path.read_text())
            except Exception:
                cache[symbol] = None
    bars = cache[symbol]
    if not bars:
        return None
    event_date = str(row.get('event_date', '')).replace('.0', '')
    entry_date = str(row.get('entry_date_s', '')).replace('.0', '')
    event_idx = index_by_date(bars, event_date)
    entry_idx = index_by_date(bars, entry_date)
    if event_idx is None or entry_idx is None or event_idx < 25:
        return None

    event = bars[event_idx]
    prev20 = bars[max(0, event_idx - 20):event_idx]
    prev10 = bars[max(0, event_idx - 10):event_idx]
    if not prev20 or not prev10:
        return None

    o = float(event['o']); c = float(event['c']); h = float(event['h']); l = float(event['l'])
    rng = max(h - l, 1e-9)
    prev_high = max(float(x['h']) for x in prev20)
    prev_low = min(float(x['l']) for x in prev20)
    prev10_high = max(float(x['h']) for x in prev10)
    prev10_low = min(float(x['l']) for x in prev10)
    vols = [float(x.get('v') or 0) for x in prev20 if float(x.get('v') or 0) > 0]
    vol_mean = sum(vols) / len(vols) if vols else 0

    # Source-safe window: event through the bar before entry.  If entry is the
    # event day, use event bar only; never use entry-day high/low/close after fill.
    pre_end = max(event_idx + 1, entry_idx)
    pre = bars[event_idx:pre_end]
    min_low = min(float(x['l']) for x in pre)
    max_high = max(float(x['h']) for x in pre)
    pre_last_close = float(pre[-1]['c'])
    entry_price = float(row['entry_price'])

    return {
        'raw_event_break20_pct': (c / prev_high - 1) * 100,
        'raw_event_close_pos': (c - l) / rng,
        'raw_event_body_pct': abs(c - o) / rng * 100,
        'raw_event_volr': float(event.get('v') or 0) / vol_mean if vol_mean else None,
        'raw_prev20_range_pct': (prev_high / prev_low - 1) * 100,
        'raw_prev10_range_pct': (prev10_high / prev10_low - 1) * 100,
        'raw_preentry_min_pullback_pct': (min_low / c - 1) * 100,
        'raw_preentry_max_push_pct': (max_high / c - 1) * 100,
        'raw_preentry_last_close_vs_event_pct': (pre_last_close / c - 1) * 100,
        'raw_entry_gap_vs_preclose_pct': (entry_price / pre_last_close - 1) * 100,
    }


def pred_mask(df: pd.DataFrame, pred: tuple[str, str, Any]) -> pd.Series:
    col, op, val = pred
    if op == '==':
        return df[col].astype(str) == str(val)
    x = pd.to_numeric(df[col], errors='coerce')
    return x <= float(val) if op == '<=' else x >= float(val)


def pred_str(pred: tuple[str, str, Any]) -> str:
    col, op, val = pred
    if isinstance(val, float):
        return f'{col} {op} {val:.6g}'
    return f'{col} {op} {val}'


def build_preds(df: pd.DataFrame) -> list[tuple[str, str, Any]]:
    preds: list[tuple[str, str, Any]] = []
    numeric = [c for c in SAFE_SOURCE_FIELDS if c in df and c not in {'poi_source', 'market_state', 'v132_reclaim_class'}]
    for col in numeric:
        x = pd.to_numeric(df[col], errors='coerce').dropna()
        if len(x) < 80:
            continue
        for q in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            th = float(x.quantile(q))
            preds.append((col, '<=', th))
            preds.append((col, '>=', th))
    for col in ('poi_source', 'market_state', 'v132_reclaim_class'):
        if col in df:
            for val in df[col].dropna().astype(str).value_counts().head(6).index:
                preds.append((col, '==', val))
    return preds


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = add_key(pd.read_csv(BASELINE, low_memory=False))
    uni = add_key(pd.read_csv(UNIVERSE, low_memory=False))
    base_keys = set(base['_key'])
    child = uni[~uni['_key'].isin(base_keys)].copy()

    cache: dict[str, list[dict[str, Any]] | None] = {}
    feature_rows: list[dict[str, Any]] = []
    feature_indices: list[Any] = []
    for idx, row in child.iterrows():
        f = raw_features(row, cache)
        if f is None:
            continue
        feature_indices.append(idx)
        feature_rows.append(f)
    features_df = pd.DataFrame(feature_rows, index=feature_indices)
    child = child.join(features_df)

    selector_leak_fields = [c for c in SAFE_SOURCE_FIELDS if any(s in c.lower() for s in LEAK_FIELDS_FORBIDDEN)]
    baseline_m = metrics(base)
    frontier_rows: list[dict[str, Any]] = []
    best_rows = pd.DataFrame()

    for event_filter in ('BOS_CONTINUATION', 'SSL_SWEEP_CHOCH_REVERSAL', 'ANY'):
        sub = child.copy() if event_filter == 'ANY' else child[child['event_type'].astype(str) == event_filter].copy()
        preds = build_preds(sub)
        single_stats = []
        for p in preds:
            rows = sub[pred_mask(sub, p)].drop_duplicates('_key')
            if len(rows) < 10:
                continue
            m = metrics(rows)
            single_stats.append((p, m.get('wr', 0), m.get('avg', 0), len(rows)))
        single_stats = sorted(single_stats, key=lambda z: (z[1], z[2], z[3]), reverse=True)[:100]
        combos = [(p,) for p, *_ in single_stats] + list(combinations([x[0] for x in single_stats[:50]], 2))
        seen = set()
        for combo in combos:
            label = ' AND '.join(pred_str(p) for p in combo)
            if label in seen:
                continue
            seen.add(label)
            mask = pd.Series(True, index=sub.index)
            for p in combo:
                mask &= pred_mask(sub, p)
            rows = sub[mask].drop_duplicates('_key')
            if len(rows) < 10:
                continue
            combined = pd.concat([base, rows], ignore_index=True).drop_duplicates('_key')
            cm = metrics(combined)
            ch = metrics(rows)
            recent = rows[rows['v161_recent45'].fillna(False).astype(bool)] if 'v161_recent45' in rows else rows.iloc[0:0]
            rec = {
                'event_filter': event_filter,
                'rule': label,
                'predicates': [{'col': p[0], 'op': p[1], 'val': p[2]} for p in combo],
                'pred_count': len(combo),
                'child_n': int(len(rows)),
                'child_wr': ch.get('wr'),
                'child_avg': ch.get('avg'),
                'child_min_year_n': ch.get('min_year_n'),
                'current_recent45_hits': int(len(recent)),
                'combined_prod_pass': pass_gate(cm, PROD),
                'combined_research_pass': pass_gate(cm, RESEARCH),
                **{f'combined_{k}': v for k, v in cm.items() if k not in {'weak_months', 'year_counts', 'year_wr'}},
                'combined_year_counts': cm.get('year_counts'),
                'combined_year_wr': cm.get('year_wr'),
                'combined_weak_months': cm.get('weak_months'),
            }
            frontier_rows.append(rec)

    frontier = pd.DataFrame(frontier_rows)
    if not frontier.empty:
        frontier = frontier.sort_values(
            ['combined_prod_pass', 'combined_research_pass', 'combined_n', 'combined_wr', 'combined_avg'],
            ascending=[False, False, False, False, False],
        )
        best = frontier.iloc[0]
        # Rebuild best row set for audit export using exact predicate values, not the rounded label.
        sub = child.copy() if best['event_filter'] == 'ANY' else child[child['event_type'].astype(str) == str(best['event_filter'])].copy()
        mask = pd.Series(True, index=sub.index)
        predicates = best['predicates']
        if isinstance(predicates, str):
            predicates = json.loads(predicates)
        for p in predicates:
            mask &= pred_mask(sub, (p['col'], p['op'], p['val']))
        best_rows = sub[mask].drop_duplicates('_key')

    frontier.to_csv(OUT / 'v259_frontier.csv', index=False)
    if not best_rows.empty:
        best_rows.to_csv(OUT / 'v259_best_child_rows.csv', index=False)
        pd.concat([base, best_rows], ignore_index=True).drop_duplicates('_key').to_csv(OUT / 'v259_best_combined_rows.csv', index=False)

    summary = {
        'version': 'V259_BOS_CONTINUATION_SOURCE_SAFE_REBUILD_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'sources': {'baseline': str(BASELINE), 'universe': str(UNIVERSE)},
        'gates': {'production': PROD, 'research': RESEARCH},
        'baseline_metrics': baseline_m,
        'child_universe_rows': int(len(child)),
        'raw_feature_covered_rows': int(features_df.shape[0]),
        'selector_fields': SAFE_SOURCE_FIELDS,
        'selector_leak_fields': selector_leak_fields,
        'entry_day_high_low_close_used': False,
        'rules_tested': int(len(frontier)),
        'production_pass_count': int(frontier['combined_prod_pass'].sum()) if not frontier.empty else 0,
        'research_pass_count': int(frontier['combined_research_pass'].sum()) if not frontier.empty else 0,
        'top_candidates': frontier.head(20).to_dict('records') if not frontier.empty else [],
        'best_child_rows': str(OUT / 'v259_best_child_rows.csv') if not best_rows.empty else None,
        'best_combined_rows': str(OUT / 'v259_best_combined_rows.csv') if not best_rows.empty else None,
        'decision': 'V259_SOURCE_SAFE_BOS_CONTINUATION_PRODUCTION_GATE_PASS__NO_WRITE__NEEDS_INDEPENDENT_AUDIT_AND_CURRENT_SMOKE'
        if (not frontier.empty and bool(frontier.iloc[0]['combined_prod_pass']))
        else 'V259_NO_PRODUCTION_GATE_PASS__NO_WRITE',
    }
    (OUT / 'v259_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
