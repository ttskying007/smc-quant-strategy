#!/usr/bin/env python3
"""V320 no-write audit: fresh raw-Kline supply combined with V185 baseline.

V315-V319 closed V185 scalar filters, exit overlays, V167 supply filtering, and
full-history 60min due coverage. V320 tests a genuinely different daily raw-Kline
supply source: V262 fresh BOS -> demand retest candidates, combined with current
V185 production baseline. It does not generate production/frontend/watchlist files.
"""
from __future__ import annotations

import json
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
BASE = ROOT / 'smc_opt_v185_combined_production_candidate' / 'v185_trades.json'
FRESH = ROOT / 'smc_audit/v262_fresh_bos_retest_generator_no_write_20260702_100027/v262_all_fresh_candidates.csv'
AUD = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v320_fresh_supply_vs_v185_no_write_{TS}'
LATEST = AUD / 'v320_fresh_supply_vs_v185_latest.json'
GATE = {'n_min': 300, 'min_year_n_min': 40, 'wr_min': 87.0, 'avg_min': 6.8, 'year_wr_min': 84.0, 'micro_max': 1.0, 't1': 0}
FEATURES = ['raw_prev20_range_pct','raw_prev10_range_pct','raw_event_body_pct','raw_event_close_pos_pct','raw_event_break20_pct','raw_event_volr','risk_pct','entry_chase_above_zone_pct','event_to_reclaim_bars','zone_width_pct']


def dkey(v: Any) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def prep_base() -> pd.DataFrame:
    rows = json.load(open(BASE))
    df = pd.DataFrame(rows)
    df['entry_date_s'] = df['entry_date'].map(dkey)
    df['_key'] = df['symbol'].astype(str) + '|' + df['entry_date_s'].astype(str)
    df['t1_violation'] = df['entry_date_s'] == df.get('exit_date', '').astype(str).map(dkey)
    return df


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {'n': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    years = df['entry_date_s'].astype(str).str[:4]
    yc = years.value_counts().sort_index().to_dict()
    yw = {str(y): round(float((pnl[years == y] >= 0.8).mean() * 100), 4) for y in sorted(years.dropna().unique()) if str(y)}
    return {
        'n': int(len(df)),
        'wr': round(float((pnl >= 0.8).mean() * 100), 4),
        'gross_wr': round(float((pnl > 0).mean() * 100), 4),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss_pct': round(float((pnl < 0).mean() * 100), 4),
        'micro_profit_pct': round(float(((pnl > 0) & (pnl < 0.8)).mean() * 100), 4),
        'min_year_n': int(min(yc.values()) if yc else 0),
        'year_counts': {str(k): int(v) for k, v in yc.items()},
        'year_wr': yw,
        'all_year_wr_min': round(float(min(yw.values()) if yw else 0), 4),
        'same_day_exit_violations': int(df.get('t1_violation', pd.Series(False, index=df.index)).fillna(False).astype(bool).sum()),
        'exit_counts': {str(k): int(v) for k, v in df.get('exit_reason', pd.Series('', index=df.index)).fillna('').astype(str).value_counts().to_dict().items()},
    }


def pass_gate(m: dict[str, Any]) -> bool:
    return (
        m.get('n', 0) >= GATE['n_min'] and m.get('min_year_n', 0) >= GATE['min_year_n_min']
        and m.get('wr', 0) >= GATE['wr_min'] and m.get('avg', 0) >= GATE['avg_min']
        and m.get('all_year_wr_min', 0) >= GATE['year_wr_min'] and m.get('micro_profit_pct', 999) <= GATE['micro_max']
        and m.get('same_day_exit_violations', 0) == GATE['t1']
    )


def mask(df: pd.DataFrame, preds: tuple[tuple[str, str, float], ...]) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for c, op, v in preds:
        x = pd.to_numeric(df[c], errors='coerce')
        m &= (x <= v) if op == '<=' else (x >= v)
    return m


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = prep_base()
    fresh = pd.read_csv(FRESH, low_memory=False)
    fresh['entry_date_s'] = fresh['entry_date_s'].astype(str).str.replace('.0', '', regex=False).map(dkey)
    fresh['_key'] = fresh['symbol'].astype(str) + '|' + fresh['entry_date_s'].astype(str)
    hist = fresh[fresh['pnl_pct'].notna()].copy()
    non = hist[~hist['_key'].isin(set(base['_key']))].copy()
    non = non[non['entry_date_s'].astype(str).str[:4].isin(['2023','2024','2025','2026'])].copy()
    atoms = []
    for col in FEATURES:
        vals = pd.to_numeric(non[col], errors='coerce').dropna()
        if vals.empty:
            continue
        for q in [0.15,0.25,0.35,0.50,0.65,0.75,0.85]:
            th = round(float(vals.quantile(q)), 4)
            atoms.append((col, '<=', th)); atoms.append((col, '>=', th))
    results = []
    combos = [(a,) for a in atoms] + [p for p in combinations(atoms, 2) if p[0][0] != p[1][0]]
    for preds in combos:
        child = non[mask(non, preds)].copy()
        if len(child) < 20 or len(child) > 1200:
            continue
        combined = pd.concat([base, child], ignore_index=True, sort=False).drop_duplicates('_key', keep='first')
        cm = metrics(combined); chm = metrics(child)
        cm['gate_status'] = 'PRODUCTION_PASS' if pass_gate(cm) else 'FAIL'
        cm['rule'] = ' AND '.join(f'{c}{op}{v}' for c, op, v in preds)
        cm['child_n'] = chm.get('n', 0); cm['child_wr'] = chm.get('wr', 0); cm['child_avg'] = chm.get('avg', 0)
        cm['pred_count'] = len(preds)
        results.append(cm)
    ranked = sorted(results, key=lambda x: (x['gate_status'] == 'PRODUCTION_PASS', x['wr'], x['avg'], x['all_year_wr_min'], x['n']), reverse=True)
    pass_rows = [r for r in ranked if r['gate_status'] == 'PRODUCTION_PASS']
    best = ranked[0] if ranked else {}
    report = {
        'version': 'V320_FRESH_SUPPLY_VS_V185_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'v185': str(BASE), 'fresh_supply': str(FRESH)}, 'gate': GATE,
        'baseline_v185': metrics(base), 'fresh_raw_nonoverlap_metrics': metrics(non),
        'coverage': {'fresh_hist_rows': int(len(hist)), 'fresh_nonoverlap_2023_2026': int(len(non)), 'atoms': len(atoms), 'rules_tested': len(results)},
        'production_pass_count': len(pass_rows), 'production_pass_top20': pass_rows[:20], 'frontier_top30': ranked[:30], 'best_policy': best,
        'decision': 'V320_FRESH_SUPPLY_PASS__REQUIRES_CURRENT_SCANNER_SMOKE' if pass_rows else 'NO_V320_FRESH_SUPPLY_PROMOTION__KEEP_V185',
        'artifacts': {'report': str(OUT / 'v320_report.json'), 'all_results': str(OUT / 'v320_all_results.json'), 'latest': str(LATEST)},
    }
    json.dump(report, open(OUT / 'v320_report.json','w'), ensure_ascii=False, indent=2)
    json.dump(ranked, open(OUT / 'v320_all_results.json','w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST,'w'), ensure_ascii=False, indent=2)
    print(json.dumps({'latest': str(LATEST), 'baseline': report['baseline_v185'], 'fresh_raw': report['fresh_raw_nonoverlap_metrics'], 'coverage': report['coverage'], 'production_pass_count': len(pass_rows), 'decision': report['decision'], 'best_policy': best}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
