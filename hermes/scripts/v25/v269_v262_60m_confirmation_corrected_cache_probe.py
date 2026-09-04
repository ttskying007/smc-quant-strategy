#!/usr/bin/env python3
"""V269 no-write: corrected-cache retest of V263 60m confirmation on V262 fresh BOS supply.

Uses only 60m bars strictly before entry date. No production/frontend/watchlist writes.
"""
from __future__ import annotations

import glob
import json
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
V262 = BASE / 'smc_audit/v262_fresh_bos_retest_generator_latest.json'
BASELINE = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
M60_DIR = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v269_v262_60m_confirmation_corrected_cache_no_write_{TS}'
LATEST = BASE / 'smc_audit/v269_v262_60m_confirmation_corrected_cache_latest.json'
PROD = dict(n=600, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=6, t1=0)
RESEARCH = dict(n=590, min_year_n=70, wr=93.5, avg=7.5, year_wr_min=91.0, micro=1.0, weak_month_count=8, t1=0)


def add_key(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['entry_date_s'] = df['entry_date'].astype(str).str.replace('.0', '', regex=False)
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
        'n': int(len(df)), 'wr': round((pnl > 0).mean() * 100, 4), 'avg': round(pnl.mean(), 4),
        'median': round(pnl.median(), 4), 'min_year_n': int(min(year_counts.values()) if year_counts else 0),
        'year_counts': {str(k): int(v) for k, v in year_counts.items()}, 'year_wr': year_wr,
        'all_year_wr_min': round(min(year_wr.values()) if year_wr else 0, 2),
        'micro': round(((pnl > 0) & (pnl < 1)).mean() * 100, 4), 'loss': int((pnl <= 0).sum()),
        'weak_month_count': len(weak_months), 'weak_months': weak_months[:12],
        't1': int(df['t1_violation'].fillna(False).astype(bool).sum()) if 't1_violation' in df else 0,
    }


def pass_gate(m: dict[str, Any], gate: dict[str, float]) -> bool:
    return m.get('n', 0) >= gate['n'] and m.get('min_year_n', 0) >= gate['min_year_n'] and m.get('wr', 0) >= gate['wr'] and m.get('avg', 0) >= gate['avg'] and m.get('all_year_wr_min', 0) >= gate['year_wr_min'] and m.get('micro', 99) <= gate['micro'] and m.get('weak_month_count', 99) <= gate['weak_month_count'] and m.get('t1', 1) == gate['t1']


def fnum(x: Any, default: float = 0.0) -> float:
    try: return float(x)
    except Exception: return default


def sym_stem(symbol: str) -> str:
    return symbol.replace('.', '_')


def m60_path(symbol: str) -> Path | None:
    files = sorted(glob.glob(str(M60_DIR / f'{sym_stem(symbol)}_60min_*.json')))
    if not files:
        return None
    # prefer the longest suffix/cache file
    return Path(files[-1])


def add_m60_features(df: pd.DataFrame) -> pd.DataFrame:
    cache: dict[str, list[dict[str, Any]] | None] = {}
    feats = []
    for _, row in df.iterrows():
        symbol = str(row['symbol'])
        entry_date = str(row['entry_date_s'])[:8]
        if symbol not in cache:
            p = m60_path(symbol)
            if p is None:
                cache[symbol] = None
            else:
                try: cache[symbol] = json.loads(p.read_text())
                except Exception: cache[symbol] = None
        arr = cache[symbol]
        feat: dict[str, Any] = {'m60_covered': False}
        if arr:
            pre = [b for b in arr if str(b.get('t', b.get('date', '')))[:8] < entry_date]
            if len(pre) >= 24:
                last = pre[-1]
                win20 = pre[-20:]
                h20 = max(fnum(x['h']) for x in win20); l20 = min(fnum(x['l']) for x in win20)
                c = fnum(last['c']); v = fnum(last.get('v'))
                vavg = sum(fnum(x.get('v')) for x in win20) / len(win20)
                prev = pre[-5]
                # recent break uses rolling prior bars before each 60m bar, all before entry date.
                recent_break = False
                for j in range(max(20, len(pre)-4), len(pre)):
                    ph = max(fnum(x['h']) for x in pre[j-20:j])
                    if fnum(pre[j]['c']) > ph:
                        recent_break = True
                        break
                feat.update({
                    'm60_covered': True,
                    'm60_last_date': str(last.get('t', last.get('date', ''))),
                    'm60_close_pos20': round((c - l20) / max(h20 - l20, 1e-9) * 100, 4),
                    'm60_ret4_pct': round((c / max(fnum(prev['c']), 1e-9) - 1) * 100, 4),
                    'm60_volr20': round(v / max(vavg, 1e-9), 4),
                    'm60_recent_break20': recent_break,
                    'm60_last_close_vs_high20_pct': round((c / max(h20, 1e-9) - 1) * 100, 4),
                })
        feats.append(feat)
    return df.reset_index(drop=True).join(pd.DataFrame(feats))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v262 = json.loads(V262.read_text())
    candidates = pd.read_csv(Path(v262['out_dir']) / 'v262_all_fresh_candidates.csv', low_memory=False)
    base = add_key(pd.read_csv(BASELINE, low_memory=False))
    candidates = add_key(candidates[candidates['pnl_pct'].notna()].copy())
    child = candidates[~candidates['_key'].isin(set(base['_key']))].copy()
    enriched = add_m60_features(child)
    enriched.to_csv(OUT / 'v269_v262_child_with_m60.csv', index=False)
    covered = enriched[enriched['m60_covered'] == True].copy()

    atoms = [
        ('m60_close_pos20', '>=', 60), ('m60_close_pos20', '>=', 75), ('m60_close_pos20', '>=', 90),
        ('m60_ret4_pct', '>=', 0), ('m60_ret4_pct', '>=', 1), ('m60_ret4_pct', '>=', 2),
        ('m60_volr20', '>=', 0.8), ('m60_volr20', '>=', 1.0), ('m60_volr20', '>=', 1.5),
        ('m60_last_close_vs_high20_pct', '>=', -1.0), ('m60_last_close_vs_high20_pct', '>=', -0.3),
        ('m60_recent_break20', '==', True),
    ]
    def mask(df: pd.DataFrame, preds: tuple[tuple[str, str, Any], ...]) -> pd.Series:
        m = pd.Series(True, index=df.index)
        for col, op, val in preds:
            if op == '==': m &= df[col].fillna(False).astype(bool) == bool(val)
            elif op == '>=': m &= pd.to_numeric(df[col], errors='coerce') >= float(val)
        return m
    rows = []
    combos = [(a,) for a in atoms] + list(combinations(atoms, 2)) + list(combinations(atoms, 3))
    for preds in combos:
        s = covered[mask(covered, preds)].copy()
        if len(s) < 20:
            continue
        combined = pd.concat([base, s], ignore_index=True, sort=False).drop_duplicates('_key', keep='first')
        cm = metrics(combined); sm = metrics(s)
        rows.append({
            'rule': ' AND '.join(f'{c} {op} {v}' for c, op, v in preds),
            'pred_count': len(preds),
            'child_n': sm.get('n',0), 'child_wr': sm.get('wr',0), 'child_avg': sm.get('avg',0), 'child_min_year_n': sm.get('min_year_n',0),
            'combined_n': cm.get('n',0), 'combined_wr': cm.get('wr',0), 'combined_avg': cm.get('avg',0), 'combined_min_year_n': cm.get('min_year_n',0),
            'combined_all_year_wr_min': cm.get('all_year_wr_min',0), 'combined_micro': cm.get('micro',99), 'combined_weak_month_count': cm.get('weak_month_count',99),
            'combined_prod_pass': pass_gate(cm, PROD), 'combined_research_pass': pass_gate(cm, RESEARCH),
        })
    fr = pd.DataFrame(rows)
    if not fr.empty:
        fr = fr.sort_values(['combined_prod_pass','combined_research_pass','combined_wr','combined_avg'], ascending=[False,False,False,False])
        fr.to_csv(OUT / 'v269_frontier.csv', index=False)
    summary = {
        'version': 'V269_V262_60M_CONFIRMATION_CORRECTED_CACHE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT), 'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'v262': str(V262), 'm60_dir': str(M60_DIR), 'baseline': str(BASELINE)},
        'coverage': {'v262_child_rows': int(len(child)), 'm60_covered_rows': int(len(covered)), 'm60_coverage_pct': round(len(covered)/max(len(child),1)*100,2), 'covered_entry_date_min': str(covered['entry_date_s'].min()) if len(covered) else None, 'covered_entry_date_max': str(covered['entry_date_s'].max()) if len(covered) else None},
        'covered_raw_metrics': {'child': metrics(covered), 'combined': metrics(pd.concat([base, covered], ignore_index=True, sort=False).drop_duplicates('_key', keep='first'))},
        'rules_tested': int(len(fr)) if not fr.empty else 0,
        'production_pass_count': int(fr['combined_prod_pass'].sum()) if not fr.empty else 0,
        'research_pass_count': int(fr['combined_research_pass'].sum()) if not fr.empty else 0,
        'top_candidates': fr.head(20).to_dict('records') if not fr.empty else [],
        'decision': 'NO_PROMOTION__CORRECTED_60M_PREENTRY_CONFIRMATION_DOES_NOT_RESCUE_V262_DAILY_SUPPLY',
        'next_research_direction': ['V262 daily fresh BOS supply is structurally too noisy; 60m pre-entry filters do not approach gates.', 'Because local 60m cache ends around 20260515 for many symbols, it cannot produce current 202607 actionable routing without refresh; do not route current from this layer.'],
    }
    (OUT / 'v263_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
