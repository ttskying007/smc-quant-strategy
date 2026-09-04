#!/usr/bin/env python3
from __future__ import annotations

import json, math, hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
import pandas as pd

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
SRC = AUDIT / 'v244_post_v243_industry_participation_probe_no_write_20260701_151619/v244_best_rows.csv'
V246 = AUDIT / 'v246_industry_addback_candidate_latest.json'
OUT = AUDIT / ('v248_v246_independent_audit_no_write_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
OUT.mkdir(parents=True, exist_ok=True)

PROD = {'n': 570, 'min_year_n': 70, 'wr': 93.0, 'avg': 7.6, 'all_year_wr_min': 91.0, 'micro': 1.0, 't1': 0}
BAD_TOKENS = ['pnl', 'exit_', 'won', 'mae', 'mfe', 'hold_bars', 'rr_realized', 'base_', 'v211_pnl', 'hit_', 'future', 'after', 'post_exit']
SELECTOR_FIELDS = ['v244_industry', 'v244_ind_strong1_pct', 'v236_br_above_ma20']
WEAK_INDUSTRIES = {'C27医药制造业', 'C32有色金属冶炼和压延加工业'}
IND_STRONG_MIN = 31.1688
BROAD_BR_MIN = 46.8561

def dn(x) -> str:
    s = ''.join(ch for ch in str(x or '').replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''

def sf(x, default=math.nan) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if not math.isnan(v) else default
    except Exception:
        return default

def metrics(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return dict(n=0, wr=0, avg=0, median=0, min_year_n=0, year_counts={}, year_wr={}, all_year_wr_min=0, micro_profit_pct=0, loss_n=0, t1=0)
    p = pd.to_numeric(df['pnl_pct'], errors='coerce')
    yrs = df['entry_date'].astype(str).str[:4]
    yc = yrs.value_counts().sort_index().to_dict()
    ywr = {str(y): round(float((p[yrs == y] > 0).mean() * 100), 2) for y in sorted(yrs.dropna().unique())}
    t1 = int(((df['exit_date'].map(dn) == df['entry_date'].map(dn)) & df['exit_date'].map(dn).ne('')).sum()) if 'exit_date' in df else 0
    return dict(
        n=int(len(df)), wr=round(float((p > 0).mean() * 100), 4), avg=round(float(p.mean()), 4), median=round(float(p.median()), 4),
        min_year_n=int(min(yc.values()) if yc else 0), year_counts={str(k): int(v) for k, v in yc.items()}, year_wr=ywr,
        all_year_wr_min=round(float(min(ywr.values()) if ywr else 0), 2), micro_profit_pct=round(float(((p > 0) & (p < 1)).mean() * 100), 4),
        loss_n=int((p <= 0).sum()), t1=t1,
    )

def pass_gate(m: dict, gate: dict = PROD) -> bool:
    return all([
        m['n'] >= gate['n'], m['min_year_n'] >= gate['min_year_n'], m['wr'] >= gate['wr'], m['avg'] >= gate['avg'],
        m['all_year_wr_min'] >= gate['all_year_wr_min'], m['micro_profit_pct'] <= gate['micro'], m['t1'] == gate['t1'],
    ])

def stable_hash(df: pd.DataFrame) -> str:
    cols = [c for c in ['symbol', 'entry_date', 'exit_date', 'pnl_pct', 'v244_industry', 'v244_ind_strong1_pct', 'v236_br_above_ma20'] if c in df.columns]
    s = df[cols].astype(str).sort_values(cols[:2]).to_csv(index=False)
    return hashlib.sha256(s.encode()).hexdigest()

def period_metrics(df: pd.DataFrame, period: str) -> pd.DataFrame:
    rows = []
    if period == 'month':
        labels = df['entry_date'].astype(str).str[:6]
    elif period == 'quarter':
        yyyy = df['entry_date'].astype(str).str[:4]
        mm = pd.to_numeric(df['entry_date'].astype(str).str[4:6], errors='coerce').fillna(0).astype(int)
        labels = yyyy + 'Q' + (((mm - 1) // 3) + 1).astype(str)
    else:
        raise ValueError(period)
    tmp = df.copy(); tmp['_period'] = labels
    for k, g in tmp.groupby('_period'):
        rows.append({'period': str(k), **metrics(g.drop(columns=['_period']))})
    return pd.DataFrame(rows).sort_values('period') if rows else pd.DataFrame()

def rolling_metrics(df: pd.DataFrame, window: int = 100) -> dict:
    d = df.sort_values(['entry_date', 'symbol']).reset_index(drop=True)
    p = pd.to_numeric(d['pnl_pct'], errors='coerce')
    rows = []
    if len(d) >= window:
        for i in range(0, len(d) - window + 1):
            sub = d.iloc[i:i+window]
            sp = p.iloc[i:i+window]
            rows.append({'start': sub.iloc[0]['entry_date'], 'end': sub.iloc[-1]['entry_date'], 'wr': float((sp > 0).mean()*100), 'avg': float(sp.mean()), 'loss_n': int((sp <= 0).sum())})
    if not rows:
        return {'window': window, 'count': 0}
    r = pd.DataFrame(rows)
    r.to_csv(OUT / f'v248_rolling_{window}.csv', index=False)
    worst = r.sort_values(['wr', 'avg']).iloc[0].to_dict()
    return {'window': window, 'count': int(len(r)), 'min_wr': round(float(r.wr.min()), 2), 'min_avg': round(float(r.avg.min()), 4), 'max_loss_n': int(r.loss_n.max()), 'worst_window': worst}

raw = pd.read_csv(SRC, low_memory=False)
raw['entry_date'] = raw['entry_date'].map(dn)
raw['exit_date'] = raw['exit_date'].map(dn)
for f in SELECTOR_FIELDS:
    if f not in raw.columns:
        raise RuntimeError(f'missing selector field {f}')

ind = raw['v244_industry'].astype(str)
weak = ind.isin(WEAK_INDUSTRIES)
addback = (pd.to_numeric(raw['v244_ind_strong1_pct'], errors='coerce') >= IND_STRONG_MIN) | (pd.to_numeric(raw['v236_br_above_ma20'], errors='coerce') >= BROAD_BR_MIN)
selected = raw[(~weak) | (weak & addback)].copy()
excluded = raw[~((~weak) | (weak & addback))].copy()

# Independent CSV equality check against materialized V246 artifact.
v246_summary = json.loads(V246.read_text())
materialized_path = Path(v246_summary['out_dir']) / 'v246_selected_rows.csv'
mat = pd.read_csv(materialized_path, low_memory=False)
mat['entry_date'] = mat['entry_date'].map(dn); mat['exit_date'] = mat['exit_date'].map(dn)
recomputed_keys = set(zip(selected.symbol.astype(str), selected.entry_date.astype(str)))
mat_keys = set(zip(mat.symbol.astype(str), mat.entry_date.astype(str)))

# Duplicates and provenance.
key_counts = Counter(zip(selected.symbol.astype(str), selected.entry_date.astype(str)))
duplicates = [{'symbol': k[0], 'entry_date': k[1], 'count': v} for k, v in key_counts.items() if v > 1]
source_keys = set(zip(raw.symbol.astype(str), raw.entry_date.astype(str)))
provenance_missing = [k for k in recomputed_keys if k not in source_keys]

# Leakage check: selector names + actual selected columns used by rule.
selector_leak_fields = [f for f in SELECTOR_FIELDS if any(tok in f.lower() for tok in BAD_TOKENS)]
selector_nulls = {f: int(selected[f].isna().sum()) for f in SELECTOR_FIELDS}
selector_coverage = {f: round(float(selected[f].notna().mean() * 100), 4) for f in SELECTOR_FIELDS}

# Stability diagnostics.
month_df = period_metrics(selected, 'month'); month_df.to_csv(OUT / 'v248_selected_monthly.csv', index=False)
quarter_df = period_metrics(selected, 'quarter'); quarter_df.to_csv(OUT / 'v248_selected_quarterly.csv', index=False)
weak_months = month_df[(month_df['n'] >= 8) & ((month_df['wr'] < 85) | (month_df['avg'] < 4))].to_dict('records') if len(month_df) else []
weak_quarters = quarter_df[(quarter_df['n'] >= 20) & ((quarter_df['wr'] < 88) | (quarter_df['avg'] < 5))].to_dict('records') if len(quarter_df) else []

# Bucket and loss diagnostics.
bucket_rows = []
for name, d in [('selected', selected), ('excluded', excluded), ('weak_all', raw[weak]), ('weak_addback', raw[weak & addback]), ('weak_excluded', raw[weak & ~addback]), ('non_weak', raw[~weak])]:
    bucket_rows.append({'bucket': name, **metrics(d)})
pd.DataFrame(bucket_rows).to_csv(OUT / 'v248_bucket_metrics.csv', index=False)

loss = selected[pd.to_numeric(selected['pnl_pct'], errors='coerce') <= 0].copy()
loss_tables = {}
for c in ['v244_industry', 'source_engine', 'event_type', 'poi_source', 'market_state', 'exit_reason']:
    if c in selected.columns:
        tab = selected.groupby(c, dropna=False).apply(lambda g: pd.Series(metrics(g)), include_groups=False).reset_index()
        tab.to_csv(OUT / f'v248_by_{c}.csv', index=False)
        loss_tables[c] = loss[c].astype(str).value_counts().head(10).to_dict() if c in loss.columns else {}

selected.to_csv(OUT / 'v248_recomputed_selected_rows.csv', index=False)
excluded.to_csv(OUT / 'v248_recomputed_excluded_rows.csv', index=False)

selected_m = metrics(selected)
summary = {
    'version': 'V248_V246_INDEPENDENT_AUDIT_NO_WRITE',
    'generated_at': datetime.now().isoformat(timespec='seconds'),
    'out_dir': str(OUT),
    'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
    'source_rows': str(SRC),
    'v246_summary_source': str(V246),
    'rule_recomputed_independently': 'exclude weak industries C27/C32 unless previous-day industry strong1 >=31.1688 OR previous-day broad br_above_ma20 >=46.8561',
    'selected': selected_m,
    'excluded': metrics(excluded),
    'production_gate': PROD,
    'production_pass': pass_gate(selected_m),
    'materialized_selected_csv': str(materialized_path),
    'materialized_match': {
        'same_key_set': recomputed_keys == mat_keys,
        'missing_in_materialized': len(recomputed_keys - mat_keys),
        'extra_in_materialized': len(mat_keys - recomputed_keys),
        'recomputed_hash': stable_hash(selected),
        'materialized_hash': stable_hash(mat),
    },
    'duplicate_symbol_entry_count': len(duplicates),
    'provenance_missing_count': len(provenance_missing),
    'selector_fields': SELECTOR_FIELDS,
    'selector_leak_fields': selector_leak_fields,
    'selector_nulls': selector_nulls,
    'selector_coverage_pct': selector_coverage,
    'monthly': {'months': int(len(month_df)), 'weak_months_n_ge_8': weak_months[:20], 'weak_month_count': int(len(weak_months))},
    'quarterly': {'quarters': int(len(quarter_df)), 'weak_quarters_n_ge_20': weak_quarters[:20], 'weak_quarter_count': int(len(weak_quarters))},
    'rolling_100': rolling_metrics(selected, 100),
    'loss_n': int(len(loss)),
    'loss_top_buckets': loss_tables,
}

hard_fail = []
if not summary['production_pass']: hard_fail.append('production_gate_fail')
if selector_leak_fields: hard_fail.append('selector_leak_fields')
if len(duplicates): hard_fail.append('duplicate_symbol_entry')
if len(provenance_missing): hard_fail.append('provenance_missing')
if not summary['materialized_match']['same_key_set']: hard_fail.append('materialized_key_mismatch')
if selected_m['t1'] != 0: hard_fail.append('t1_violation')

# Do not make monthly/rolling a hard failure; they are risk diagnostics for next research.
summary['hard_failures'] = hard_fail
if hard_fail:
    summary['decision'] = 'V248_V246_INDEPENDENT_AUDIT_FAIL__NO_WRITE'
elif summary['monthly']['weak_month_count'] or summary['quarterly']['weak_quarter_count']:
    summary['decision'] = 'V248_V246_HISTORICAL_GATE_PASS_WITH_LOCAL_STABILITY_RISK__NO_WRITE__CURRENT_SCANNER_STILL_REQUIRED'
else:
    summary['decision'] = 'V248_V246_INDEPENDENT_HISTORICAL_PASS__NO_WRITE__CURRENT_SCANNER_STILL_REQUIRED'

(OUT / 'v248_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
(AUDIT / 'v248_v246_independent_audit_latest.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False, indent=2))
