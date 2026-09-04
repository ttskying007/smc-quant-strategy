#!/usr/bin/env python3
"""V267 no-write: industry rotation + stock retest source-layer probe.

Purpose after V262/V264/V265/V266 daily-only failures:
- introduce a cross-sectional industry source layer (breadth/momentum/turnover proxy)
- generate non-V246 current-compatible supply from raw daily bars + industry map
- never write production/frontend/watchlist artifacts

All selector fields are pre-entry only. Entry is next trading day after reclaim. Exit is
strict T+1 compatible: earliest exit is the bar after entry.
"""
from __future__ import annotations

import glob
import json
import math
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KLINE_DIR = BASE / 'kline_cache'
INDUSTRY = BASE / 'smc_audit/v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
BASELINE = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v267_industry_rotation_retest_source_no_write_{TS}'
LATEST = BASE / 'smc_audit/v267_industry_rotation_retest_source_latest.json'
PROD = dict(n=600, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=6, t1=0)
RESEARCH = dict(n=590, min_year_n=70, wr=93.5, avg=7.5, year_wr_min=91.0, micro=1.0, weak_month_count=8, t1=0)


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return default


def symbol_from_path(path: str) -> str:
    name = Path(path).name
    parts = name.split('_')
    return f'{parts[0]}.{parts[1]}'


def add_key(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['entry_date_s'] = df['entry_date'].astype(str).str.replace('.0', '', regex=False).str[:8]
    df['_key'] = df['symbol'].astype(str) + '|' + df['entry_date_s']
    return df


def load_industry_map() -> dict[str, str]:
    rows = json.loads(INDUSTRY.read_text())
    mp: dict[str, str] = {}
    for r in rows:
        sym = str(r.get('symbol', ''))
        ind = str(r.get('industry', '')).strip()
        if sym and ind:
            mp[sym] = ind
    return mp


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0}
    df = add_key(df) if 'entry_date_s' not in df else df.copy()
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
        'weak_month_count': len(weak_months), 'weak_months': weak_months[:15],
        't1': int(df['t1_violation'].fillna(False).astype(bool).sum()) if 't1_violation' in df else 0,
    }


def pass_gate(m: dict[str, Any], gate: dict[str, float]) -> bool:
    return (
        m.get('n', 0) >= gate['n'] and m.get('min_year_n', 0) >= gate['min_year_n']
        and m.get('wr', 0) >= gate['wr'] and m.get('avg', 0) >= gate['avg']
        and m.get('all_year_wr_min', 0) >= gate['year_wr_min'] and m.get('micro', 99) <= gate['micro']
        and m.get('weak_month_count', 99) <= gate['weak_month_count'] and m.get('t1', 1) == gate['t1']
    )


def load_symbol_bars(industry_map: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for p in glob.glob(str(KLINE_DIR / '*_daily_750.json')):
        sym = symbol_from_path(p)
        if sym not in industry_map:
            continue
        try:
            arr = json.loads(Path(p).read_text())
        except Exception:
            continue
        bars = []
        for b in arr:
            c = fnum(b.get('c'))
            if c <= 0:
                continue
            bars.append({'t': str(b.get('t', b.get('date', '')))[:8], 'o': fnum(b.get('o')), 'h': fnum(b.get('h')), 'l': fnum(b.get('l')), 'c': c, 'v': fnum(b.get('v'))})
        if len(bars) >= 120:
            out[sym] = bars
    return out


def build_industry_features(symbol_bars: dict[str, list[dict[str, Any]]], industry_map: dict[str, str]) -> dict[tuple[str, str], dict[str, float]]:
    agg: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {'n': 0, 'ret5': 0.0, 'ret20': 0.0, 'above20': 0, 'above60': 0, 'limitup': 0, 'turnover': 0.0})
    for sym, bars in symbol_bars.items():
        ind = industry_map[sym]
        closes = [b['c'] for b in bars]
        for i in range(60, len(bars)):
            c = closes[i]
            ma20 = sum(closes[i-19:i+1]) / 20
            ma60 = sum(closes[i-59:i+1]) / 60
            ret5 = (c / closes[i-5] - 1) * 100
            ret20 = (c / closes[i-20] - 1) * 100
            prev_c = closes[i-1]
            a = agg[(ind, bars[i]['t'])]
            a['n'] += 1
            a['ret5'] += ret5
            a['ret20'] += ret20
            a['above20'] += int(c > ma20)
            a['above60'] += int(c > ma60)
            a['limitup'] += int(c / prev_c - 1 >= 0.095)
            a['turnover'] += c * bars[i]['v']
    # first pass averages
    by_date: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    feats: dict[tuple[str, str], dict[str, float]] = {}
    for key, a in agg.items():
        n = max(a['n'], 1)
        f = {
            'ind_n': n,
            'ind_ret5': a['ret5'] / n,
            'ind_ret20': a['ret20'] / n,
            'ind_breadth20': a['above20'] / n * 100,
            'ind_breadth60': a['above60'] / n * 100,
            'ind_limitup_pct': a['limitup'] / n * 100,
            'ind_turnover': a['turnover'],
        }
        feats[key] = f
        by_date[key[1]].append((key[0], f))
    # add cross-sectional ranks per date
    for date, rows in by_date.items():
        rows = [r for r in rows if r[1]['ind_n'] >= 8]
        rows5 = sorted(rows, key=lambda x: x[1]['ind_ret5'], reverse=True)
        rows20 = sorted(rows, key=lambda x: x[1]['ind_ret20'], reverse=True)
        rowst = sorted(rows, key=lambda x: x[1]['ind_turnover'], reverse=True)
        for rank, (ind, _) in enumerate(rows5, 1):
            feats[(ind, date)]['ind_rank_ret5'] = rank
        for rank, (ind, _) in enumerate(rows20, 1):
            feats[(ind, date)]['ind_rank_ret20'] = rank
        for rank, (ind, _) in enumerate(rowst, 1):
            feats[(ind, date)]['ind_rank_turnover'] = rank
    return feats


def simulate_exit(bars: list[dict[str, Any]], entry_idx: int, entry_price: float, sl: float, tp: float, max_hold: int = 10) -> dict[str, Any]:
    end = min(len(bars) - 1, entry_idx + max_hold)
    for j in range(entry_idx + 1, end + 1):  # strict T+1: no same-day exit
        b = bars[j]
        if b['l'] <= sl:
            return {'exit_idx': j, 'exit_date': b['t'], 'exit_price': sl, 'exit_reason': 'SL', 'hold_bars': j - entry_idx, 'pnl_pct': (sl / entry_price - 1) * 100, 't1_violation': False}
        if b['h'] >= tp:
            return {'exit_idx': j, 'exit_date': b['t'], 'exit_price': tp, 'exit_reason': 'TP', 'hold_bars': j - entry_idx, 'pnl_pct': (tp / entry_price - 1) * 100, 't1_violation': False}
    b = bars[end]
    return {'exit_idx': end, 'exit_date': b['t'], 'exit_price': b['c'], 'exit_reason': 'TIME', 'hold_bars': end - entry_idx, 'pnl_pct': (b['c'] / entry_price - 1) * 100, 't1_violation': False}


def generate_candidates(symbol_bars: dict[str, list[dict[str, Any]]], industry_map: dict[str, str], ind_feats: dict[tuple[str, str], dict[str, float]]) -> pd.DataFrame:
    rows = []
    for sym, bars in symbol_bars.items():
        ind = industry_map[sym]
        closes = [b['c'] for b in bars]
        vols = [b['v'] for b in bars]
        for i in range(80, len(bars) - 2):
            # event: stock breaks previous 40d high inside a strong/rotating industry, all known at event close
            prev40_high = max(x['h'] for x in bars[i-40:i])
            prev20_low = min(x['l'] for x in bars[i-20:i])
            event = bars[i]
            if event['c'] <= prev40_high:
                continue
            event_ret = (event['c'] / closes[i-1] - 1) * 100
            if event_ret < 3.0:
                continue
            zone_low = prev40_high
            zone_high = event['c']
            zone_width = (zone_high / max(zone_low, 1e-9) - 1) * 100
            if zone_width <= 0 or zone_width > 18:
                continue
            evf = ind_feats.get((ind, event['t']))
            if not evf or evf.get('ind_n', 0) < 8:
                continue
            # confirmation: within next 1..8 bars pull back near broken high, hold it, and reclaim above zone midpoint
            for r in range(i + 1, min(i + 9, len(bars) - 1)):
                rb = bars[r]
                touched = rb['l'] <= zone_high and rb['l'] >= zone_low * 0.985
                reclaimed = rb['c'] > (zone_low + zone_high) / 2 and rb['c'] > rb['o']
                if not (touched and reclaimed):
                    continue
                entry_idx = r + 1
                if entry_idx >= len(bars):
                    break
                entry = bars[entry_idx]
                entry_price = entry['o']
                if entry_price <= 0:
                    break
                retest_low = min(x['l'] for x in bars[i+1:r+1])
                sl = min(zone_low, retest_low) * 0.99
                risk_pct = (entry_price / max(sl, 1e-9) - 1) * 100
                if risk_pct <= 1.0 or risk_pct > 8.0:
                    continue
                tp = entry_price + (entry_price - sl) * 1.8
                ex = simulate_exit(bars, entry_idx, entry_price, sl, tp)
                pre_vol20 = sum(vols[i-20:i]) / 20
                row = {
                    'symbol': sym, 'industry': ind, 'event_type': 'INDUSTRY_ROTATION_BREAK_RETEST',
                    'event_date': event['t'], 'event_idx': i, 'reclaim_date': rb['t'], 'reclaim_idx': r,
                    'entry_idx': entry_idx, 'entry_date': entry['t'], 'entry_date_s': entry['t'], 'entry_price': round(entry_price, 4),
                    'event_ret_pct': round(event_ret, 4), 'event_body_pct': round((event['c'] - event['o']) / max(event['h'] - event['l'], 1e-9) * 100, 4),
                    'event_volr20': round(event['v'] / max(pre_vol20, 1e-9), 4), 'prev20_range_pct': round((max(x['h'] for x in bars[i-20:i]) / max(prev20_low, 1e-9) - 1) * 100, 4),
                    'zone_width_pct': round(zone_width, 4), 'pullback_depth_pct': round((zone_high / max(retest_low, 1e-9) - 1) * 100, 4),
                    'event_to_reclaim_bars': r - i, 'reclaim_close_pos_pct': round((rb['c'] - rb['l']) / max(rb['h'] - rb['l'], 1e-9) * 100, 4),
                    'entry_chase_vs_zone_high_pct': round((entry_price / max(zone_high, 1e-9) - 1) * 100, 4),
                    'risk_pct': round(risk_pct, 4), 'tp': round(tp, 4), 'sl': round(sl, 4),
                    'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
                    **{k: round(v, 4) if isinstance(v, float) else v for k, v in evf.items()},
                    **ex,
                }
                row['_key'] = row['symbol'] + '|' + row['entry_date_s']
                rows.append(row)
                break
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates('_key', keep='first')


def apply_preds(df: pd.DataFrame, preds: tuple[tuple[str, str, Any], ...]) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for col, op, val in preds:
        s = df[col]
        if op == '>=':
            m &= pd.to_numeric(s, errors='coerce') >= float(val)
        elif op == '<=':
            m &= pd.to_numeric(s, errors='coerce') <= float(val)
    return m


def frontier_search(child: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    atoms = [
        ('ind_rank_ret5', '<=', 5), ('ind_rank_ret5', '<=', 10), ('ind_rank_ret20', '<=', 8), ('ind_rank_turnover', '<=', 12),
        ('ind_ret5', '>=', 1.5), ('ind_ret5', '>=', 3.0), ('ind_ret20', '>=', 4.0), ('ind_breadth20', '>=', 55), ('ind_breadth20', '>=', 70), ('ind_breadth60', '>=', 45),
        ('ind_limitup_pct', '>=', 2.0), ('event_ret_pct', '>=', 5.0), ('event_body_pct', '>=', 60), ('event_volr20', '>=', 1.2),
        ('prev20_range_pct', '>=', 12), ('zone_width_pct', '<=', 10), ('pullback_depth_pct', '<=', 8), ('event_to_reclaim_bars', '<=', 5),
        ('reclaim_close_pos_pct', '>=', 60), ('entry_chase_vs_zone_high_pct', '<=', 3.0), ('risk_pct', '<=', 5.0),
    ]
    combos = [(a,) for a in atoms] + list(combinations(atoms, 2)) + list(combinations(atoms, 3))
    rows = []
    for preds in combos:
        s = child[apply_preds(child, preds)].copy()
        if len(s) < 20:
            continue
        child_m = metrics(s)
        if child_m.get('wr', 0) < 55 or child_m.get('avg', -99) < 1.0:
            continue
        combined = pd.concat([base, s], ignore_index=True, sort=False).drop_duplicates('_key', keep='first')
        cm = metrics(combined)
        rows.append({
            'rule': ' AND '.join(f'{c} {op} {v}' for c, op, v in preds), 'pred_count': len(preds),
            'child_n': child_m.get('n', 0), 'child_wr': child_m.get('wr', 0), 'child_avg': child_m.get('avg', 0), 'child_min_year_n': child_m.get('min_year_n', 0),
            'combined_n': cm.get('n', 0), 'combined_wr': cm.get('wr', 0), 'combined_avg': cm.get('avg', 0), 'combined_min_year_n': cm.get('min_year_n', 0),
            'combined_all_year_wr_min': cm.get('all_year_wr_min', 0), 'combined_micro': cm.get('micro', 99), 'combined_weak_month_count': cm.get('weak_month_count', 99),
            'combined_prod_pass': pass_gate(cm, PROD), 'combined_research_pass': pass_gate(cm, RESEARCH),
        })
    fr = pd.DataFrame(rows)
    if not fr.empty:
        fr = fr.sort_values(['combined_prod_pass', 'combined_research_pass', 'combined_wr', 'combined_avg', 'child_wr'], ascending=[False, False, False, False, False])
    return fr


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ind_map = load_industry_map()
    symbol_bars = load_symbol_bars(ind_map)
    base = add_key(pd.read_csv(BASELINE, low_memory=False))
    ind_feats = build_industry_features(symbol_bars, ind_map)
    all_df = generate_candidates(symbol_bars, ind_map, ind_feats)
    if all_df.empty:
        raise SystemExit('no candidates generated')
    child = all_df[~all_df['_key'].isin(set(base['_key']))].copy()
    latest_date = str(all_df['entry_date_s'].max())
    current_cut = str((pd.to_datetime(latest_date) - pd.Timedelta(days=45)).strftime('%Y%m%d'))
    current = child[child['entry_date_s'] >= current_cut].copy()
    fr = frontier_search(child, base)

    all_df.to_csv(OUT / 'v267_all_industry_rotation_retest_candidates.csv', index=False)
    current.to_csv(OUT / 'v267_current_recent45_candidates.csv', index=False)
    fr.to_csv(OUT / 'v267_frontier.csv', index=False)
    raw_combined = pd.concat([base, child], ignore_index=True, sort=False).drop_duplicates('_key', keep='first')
    summary = {
        'version': 'V267_INDUSTRY_ROTATION_RETEST_SOURCE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'out_dir': str(OUT),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'baseline': str(BASELINE), 'kline_files': len(symbol_bars), 'industry_symbols': len(ind_map)}, 'gates': {'production': PROD, 'research': RESEARCH},
        'baseline_metrics': metrics(base),
        'generated': {'all_candidates': int(len(all_df)), 'historical_nonoverlap_vs_baseline': int(len(child)), 'current_recent45_candidates': int(len(current)), 'latest_entry_date': latest_date, 'current_cut': current_cut},
        'raw_generator_metrics': {'child': metrics(child), 'combined': metrics(raw_combined)},
        'rules_tested_after_prefilter': int(len(fr)), 'production_pass_count': int(fr['combined_prod_pass'].sum()) if not fr.empty else 0, 'research_pass_count': int(fr['combined_research_pass'].sum()) if not fr.empty else 0,
        'top_candidates': fr.head(20).to_dict('records') if not fr.empty else [],
        'current_breakdown': {
            'by_industry_top10': current['industry'].value_counts().head(10).to_dict() if not current.empty else {},
            'avg_ind_ret5': round(pd.to_numeric(current['ind_ret5'], errors='coerce').mean(), 4) if not current.empty else None,
            'avg_ind_breadth20': round(pd.to_numeric(current['ind_breadth20'], errors='coerce').mean(), 4) if not current.empty else None,
        },
        'decision': 'KEEP_SHADOW_NO_WRITE_PENDING_GATE_RESULT',
        'next_research_direction': ['If no frontier passes, industry rotation proxy is supply-positive but not production-quality; next layer must use true intraday/board-fund data, not daily-only approximations.', 'If a historical frontier passes but current rows are zero, keep shadow exactly like V259/V260.'],
    }
    if summary['production_pass_count'] > 0 and summary['generated']['current_recent45_candidates'] > 0:
        summary['decision'] = 'HISTORICAL_FRONTIER_FOUND__REQUIRES_INDEPENDENT_AUDIT_AND_CURRENT_SELECTOR_SMOKE__NO_WRITE'
    elif summary['research_pass_count'] > 0:
        summary['decision'] = 'RESEARCH_FRONTIER_ONLY__NO_WRITE'
    else:
        summary['decision'] = 'NO_PROMOTION__INDUSTRY_ROTATION_RETEST_DOES_NOT_PASS_FRONTIER'
    (OUT / 'v267_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
