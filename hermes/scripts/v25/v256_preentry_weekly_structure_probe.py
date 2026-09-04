#!/usr/bin/env python3
"""V256 no-write probe: pre-entry weekly/daily structure source layer.

Reads historical selected rows and candidate universe, computes only pre-entry
OHLCV structure features from local daily_750 cache, and searches simple gates.
No production/frontend/watchlist writes.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path('/root/.hermes')
KLINE_DIR = BASE / 'kline_cache'
SRC = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
V230 = BASE / 'smc_audit/v230_v228_plus_new_supply_expansion_probe_no_write_20260627_053747/v230_candidate_pool_enriched.csv'
CURRENT = BASE / 'smc_opt_v90_daily_full_market_scanner/v128_parallel_shadow_candidates.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v256_preentry_weekly_structure_probe_no_write_{TS}'
LATEST = BASE / 'smc_audit/v256_preentry_weekly_structure_probe_latest.json'

PROD = dict(n=570, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=1)
RESEARCH = dict(n=540, min_year_n=60, wr=94.2, avg=7.45, year_wr_min=90.0, micro=1.0, weak_month_count=2)


def sym_to_path(sym: str) -> Path:
    code, ex = str(sym).split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_750.json'


def load_bars(sym: str) -> pd.DataFrame | None:
    p = sym_to_path(sym)
    if not p.exists():
        return None
    try:
        rows = json.loads(p.read_text())
    except Exception:
        return None
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if df.empty or 't' not in df:
        return None
    for c in ['o', 'h', 'l', 'c', 'v']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['t'] = df['t'].astype(str)
    df = df.dropna(subset=['o', 'h', 'l', 'c']).sort_values('t').reset_index(drop=True)
    return df


def pct(a: float, b: float) -> float:
    if not b or pd.isna(a) or pd.isna(b):
        return math.nan
    return (a / b - 1.0) * 100.0


def max_drawup(prior: pd.DataFrame, n: int) -> float:
    w = prior.tail(n)
    if w.empty:
        return math.nan
    lo = w['l'].min(); hi = w['h'].max()
    return pct(hi, lo)


def compute_feature(row: pd.Series) -> dict:
    sym = str(row['symbol'])
    entry_date = str(int(float(row['entry_date']))) if not pd.isna(row['entry_date']) else ''
    bars = load_bars(sym)
    if bars is None:
        return {'v256_feature_ok': False}
    idxs = bars.index[bars['t'] < entry_date].tolist()
    if len(idxs) < 80:
        return {'v256_feature_ok': False}
    i = idxs[-1]
    prior = bars.iloc[: i + 1].copy()
    last = prior.iloc[-1]
    out = {'v256_feature_ok': True, 'v256_prev_date': last['t']}
    for n in (5, 10, 20, 40, 60):
        w = prior.tail(n)
        out[f'v256_ret{n}'] = pct(last['c'], w.iloc[0]['c']) if len(w) >= n else math.nan
        out[f'v256_pos{n}'] = pct(last['c'], w['l'].min()) / max(pct(w['h'].max(), w['l'].min()), 1e-9) * 100.0 if len(w) >= n else math.nan
        out[f'v256_range{n}'] = max_drawup(prior, n)
    vol20 = prior['v'].tail(20).mean()
    vol60 = prior['v'].tail(60).mean()
    out['v256_vol20_vs60'] = (vol20 / vol60) if vol60 and not pd.isna(vol60) else math.nan
    # Pure structure: last completed 5-day bars (weekly-like, no future data).
    wk = prior.copy()
    wk['g'] = (range(len(wk)))
    wk['week_bucket'] = wk['g'] // 5
    weeks = wk.groupby('week_bucket').agg(o=('o','first'), h=('h','max'), l=('l','min'), c=('c','last'), v=('v','sum')).tail(16)
    if len(weeks) >= 8:
        lastw = weeks.iloc[-1]
        prev4 = weeks.iloc[-5:-1]
        prev8 = weeks.iloc[-9:-1] if len(weeks) >= 9 else weeks.iloc[:-1]
        out['v256_w_close_pos4'] = pct(lastw['c'], prev4['l'].min()) / max(pct(prev4['h'].max(), prev4['l'].min()), 1e-9) * 100.0
        out['v256_w_break_prev4_high_pct'] = pct(lastw['c'], prev4['h'].max())
        out['v256_w_above_prev4_low_pct'] = pct(lastw['c'], prev4['l'].min())
        out['v256_w_range8'] = pct(prev8['h'].max(), prev8['l'].min())
        out['v256_w_higher_low'] = bool(lastw['l'] > prev4['l'].min())
        out['v256_w_inside_prev4'] = bool(lastw['h'] <= prev4['h'].max() and lastw['l'] >= prev4['l'].min())
    return out


def metrics(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {'n': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    entry_date = df['entry_date'].astype(str).str.replace('.0','', regex=False)
    years = entry_date.str[:4]
    months = entry_date.str[:6]
    year_counts = years.value_counts().sort_index().to_dict()
    year_wr = {y: round((pnl[years == y] > 0).mean()*100, 2) for y in sorted(years.dropna().unique())}
    month_tbl = []
    for m, g in df.groupby(months):
        gp = pd.to_numeric(g['pnl_pct'], errors='coerce')
        if len(g) >= 10:
            wr = (gp > 0).mean()*100
            avg = gp.mean()
            if wr < 90 or avg < 5.5:
                month_tbl.append({'period': str(m), 'n': int(len(g)), 'wr': round(wr,2), 'avg': round(avg,4), 'loss': int((gp<=0).sum())})
    t1 = 0
    if 't1_violation' in df:
        t1 = int(df['t1_violation'].fillna(False).astype(bool).sum())
    return {
        'n': int(n), 'wr': round((pnl > 0).mean()*100, 4), 'avg': round(pnl.mean(), 4),
        'median': round(pnl.median(), 4), 'min_year_n': int(min(year_counts.values()) if year_counts else 0),
        'year_counts': {str(k): int(v) for k,v in year_counts.items()}, 'year_wr': year_wr,
        'all_year_wr_min': round(min(year_wr.values()) if year_wr else 0, 2),
        'micro': round(((pnl > 0) & (pnl < 1)).mean()*100, 4), 'loss': int((pnl <= 0).sum()),
        't1': t1, 'weak_month_count': len(month_tbl), 'weak_months': month_tbl,
    }


def pass_gate(m: dict, gate: dict) -> bool:
    return (m.get('n',0) >= gate['n'] and m.get('min_year_n',0) >= gate['min_year_n'] and
            m.get('wr',0) >= gate['wr'] and m.get('avg',0) >= gate['avg'] and
            m.get('all_year_wr_min',0) >= gate['year_wr_min'] and m.get('micro',99) <= gate['micro'] and
            m.get('weak_month_count',99) <= gate['weak_month_count'] and m.get('t1',1) == 0)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    feats = [compute_feature(r) for _, r in df.iterrows()]
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(feats)], axis=1)


def search_rules(df: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        c for c in df.columns
        if c.startswith('v256_')
        and pd.api.types.is_numeric_dtype(df[c])
        and not pd.api.types.is_bool_dtype(df[c])
    ]
    rows = []
    for col in numeric:
        vals = df[col].dropna()
        if len(vals) < 100:
            continue
        qs = sorted(set([0.05,0.1,0.15,0.2,0.25,0.3,0.4,0.6,0.7,0.75,0.8,0.85,0.9,0.95]))
        for q in qs:
            th = float(vals.quantile(q))
            for op in ('<=','>='):
                keep = df[df[col] <= th] if op == '<=' else df[df[col] >= th]
                if len(keep) < 500:
                    continue
                m = metrics(keep)
                rows.append({'rule': f'{col} {op} {th:.6g}', 'drop': int(len(df)-len(keep)),
                             'prod_pass': pass_gate(m, PROD), 'research_pass': pass_gate(m, RESEARCH), **m})
    # two boolean gates
    for col in ['v256_w_higher_low','v256_w_inside_prev4']:
        if col in df:
            for val in [True, False]:
                keep = df[df[col] == val]
                if len(keep) >= 500:
                    m = metrics(keep)
                    rows.append({'rule': f'{col} == {val}', 'drop': int(len(df)-len(keep)),
                                 'prod_pass': pass_gate(m, PROD), 'research_pass': pass_gate(m, RESEARCH), **m})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(['prod_pass','research_pass','weak_month_count','wr','avg'], ascending=[False,False,True,False,False])


def current_coverage() -> dict:
    if not CURRENT.exists():
        return {'source_exists': False}
    data = json.loads(CURRENT.read_text())
    rows = data if isinstance(data, list) else data.get('data') or data.get('rows') or []
    df = pd.DataFrame(rows)
    if df.empty:
        return {'source_exists': True, 'rows': 0}
    if 'entry_date' not in df:
        return {'source_exists': True, 'rows': len(df), 'feature_rows': 0, 'reason': 'no entry_date'}
    df = df[df['entry_date'].notna()].copy()
    if len(df) > 300:
        df = df.tail(300)
    ef = enrich(df)
    return {'source_exists': True, 'rows_checked': int(len(df)), 'feature_ok': int(ef['v256_feature_ok'].sum()),
            'latest_entry_date': str(df['entry_date'].max()) if len(df) else None}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(SRC)
    enriched = enrich(base)
    enriched.to_csv(OUT / 'v256_selected_with_preentry_structure.csv', index=False)
    base_m = metrics(enriched)
    rules = search_rules(enriched[enriched['v256_feature_ok'] == True].copy())
    rules.to_csv(OUT / 'v256_rule_frontier.csv', index=False)
    top = rules.head(20).to_dict('records') if not rules.empty else []
    prod_count = int(rules['prod_pass'].sum()) if not rules.empty else 0
    research_count = int(rules['research_pass'].sum()) if not rules.empty else 0

    # Historical universe family sanity: do not just fit selected rows.
    universe_summary = {}
    if V230.exists():
        u = pd.read_csv(V230)
        # Only a bounded sample of historical universe to keep this probe fast and no-write.
        sample = u.sort_values('entry_date').tail(2000).copy()
        eu = enrich(sample)
        universe_summary = {
            'sample_rows': int(len(sample)),
            'feature_ok': int(eu['v256_feature_ok'].sum()),
            'family_baseline': metrics(eu[eu['v256_feature_ok'] == True]) if 'pnl_pct' in eu else {},
        }
        eu.to_csv(OUT / 'v256_recent_universe_sample_with_features.csv', index=False)

    summary = {
        'version': 'V256_PREENTRY_WEEKLY_STRUCTURE_PROBE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': str(SRC),
        'out_dir': str(OUT),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'gate': {'production': PROD, 'research': RESEARCH},
        'baseline_metrics': base_m,
        'feature_coverage': {'rows': int(len(enriched)), 'feature_ok': int(enriched['v256_feature_ok'].sum())},
        'rules_tested': int(len(rules)), 'production_pass_count': prod_count, 'research_pass_count': research_count,
        'top_candidates': top,
        'current_scanner_feature_coverage': current_coverage(),
        'universe_sample_summary': universe_summary,
        'decision': 'PENDING',
        'artifacts': {
            'selected_features': str(OUT / 'v256_selected_with_preentry_structure.csv'),
            'frontier': str(OUT / 'v256_rule_frontier.csv'),
        },
    }
    if prod_count:
        summary['decision'] = 'V256_HAS_PRODUCTION_PASSING_PREENTRY_STRUCTURE_CANDIDATE__NEEDS_INDEPENDENT_CURRENT_SMOKE'
    elif research_count:
        summary['decision'] = 'V256_RESEARCH_ONLY_PREENTRY_STRUCTURE_CANDIDATE__NO_PRODUCTION_WRITE'
    else:
        summary['decision'] = 'V256_NO_FRONTIER__WEEKLY_DAILY_PREENTRY_STRUCTURE_LAYER_CLOSED_FOR_V246_WEAK_MONTH_FIX'
    (OUT / 'v256_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
