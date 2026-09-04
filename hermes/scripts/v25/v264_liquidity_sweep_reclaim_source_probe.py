#!/usr/bin/env python3
"""V264 no-write: raw daily liquidity-sweep reclaim source-layer probe.

New source family (not V128/V230 scalar bridge):
  1) A candle sweeps below prior N-day low and reclaims above that low.
  2) The sweep candle / previous bearish candle defines a demand zone.
  3) Entry is next open after the reclaim candle.
  4) Selector uses only bars up to the reclaim candle; exit replay starts T+1.

All outputs are research-only: no production/frontend/watchlist writes.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KLINE_DIR = BASE / 'kline_cache'
BASELINE = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v264_liquidity_sweep_reclaim_source_probe_no_write_{TS}'
LATEST = BASE / 'smc_audit/v264_liquidity_sweep_reclaim_source_probe_latest.json'

PROD = dict(n=600, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=6, t1=0)
RESEARCH = dict(n=590, min_year_n=70, wr=93.5, avg=7.5, year_wr_min=91.0, micro=1.0, weak_month_count=8, t1=0)


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def date_s(bar: dict[str, Any]) -> str:
    return str(bar.get('t', bar.get('date', ''))).replace('.0', '')[:8]


def symbol_from_path(path: Path) -> str:
    stem = path.stem.replace('_daily_750', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def add_key(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['entry_date_s'] = df['entry_date'].astype(str).str.replace('.0', '', regex=False).str[:8]
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


def replay_exit(bars: list[dict[str, Any]], entry_idx: int, entry: float, sl: float, rr: float = 1.5, max_hold: int = 10) -> dict[str, Any] | None:
    first_exit = entry_idx + 1  # T+1 hard gate
    if first_exit >= len(bars):
        return None
    tp = entry + (entry - sl) * rr
    last = min(len(bars) - 1, entry_idx + max_hold)
    exit_idx = last
    exit_price = fnum(bars[last]['c'])
    reason = f'TIME{max_hold}'
    for i in range(first_exit, last + 1):
        lo = fnum(bars[i]['l']); hi = fnum(bars[i]['h'])
        if lo <= sl:
            exit_idx = i; exit_price = sl; reason = 'SL'; break
        if hi >= tp:
            exit_idx = i; exit_price = tp; reason = 'TP'; break
    return {
        'exit_idx': exit_idx,
        'exit_date': date_s(bars[exit_idx]),
        'exit_price': round(exit_price, 4),
        'exit_reason': reason,
        'tp': round(tp, 4),
        'sl': round(sl, 4),
        'pnl_pct': round((exit_price / entry - 1) * 100, 4),
        'hold_bars': int(exit_idx - entry_idx),
        't1_violation': date_s(bars[exit_idx]) == date_s(bars[entry_idx]),
    }


def generate_symbol(path: Path) -> list[dict[str, Any]]:
    symbol = symbol_from_path(path)
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    if len(bars) < 80:
        return rows
    for i in range(45, len(bars) - 11):
        b = bars[i]
        o = fnum(b['o']); h = fnum(b['h']); l = fnum(b['l']); c = fnum(b['c']); v = fnum(b.get('v'))
        if min(o, h, l, c) <= 0:
            continue
        prior20 = bars[i-20:i]
        prior10 = bars[i-10:i]
        prior40 = bars[i-40:i]
        prev_low20 = min(fnum(x['l']) for x in prior20)
        prev_low10 = min(fnum(x['l']) for x in prior10)
        prev_high20 = max(fnum(x['h']) for x in prior20)
        prev_high40 = max(fnum(x['h']) for x in prior40)
        prev_low40 = min(fnum(x['l']) for x in prior40)
        range20 = (prev_high20 / max(prev_low20, 1e-9) - 1) * 100
        range40 = (prev_high40 / max(prev_low40, 1e-9) - 1) * 100
        volr20 = v / max(sum(fnum(x.get('v')) for x in prior20) / 20, 1e-9)
        body_pct = abs(c - o) / max(h - l, 1e-9) * 100
        close_pos = (c - l) / max(h - l, 1e-9) * 100
        sweep_depth20 = (prev_low20 / max(l, 1e-9) - 1) * 100
        trend20 = (fnum(bars[i-1]['c']) / max(fnum(bars[i-20]['c']), 1e-9) - 1) * 100
        if not (l < prev_low20 and c > prev_low20 and c > o):
            continue
        if l >= prev_low10:
            continue
        zone_idx = i
        for j in range(i - 1, max(i - 8, -1), -1):
            if fnum(bars[j]['c']) < fnum(bars[j]['o']):
                zone_idx = j
                break
        z = bars[zone_idx]
        zone_low = min(fnum(z['o']), fnum(z['c']), fnum(z['l']))
        zone_high = max(fnum(z['o']), fnum(z['c']))
        if zone_low <= 0 or zone_high <= 0:
            continue
        entry_idx = i + 1
        entry = fnum(bars[entry_idx]['o'])
        if entry <= 0:
            continue
        sl = zone_low * 0.99
        risk_pct = (entry / max(sl, 1e-9) - 1) * 100
        if risk_pct <= 0 or risk_pct > 16:
            continue
        out = replay_exit(bars, entry_idx, entry, sl)
        if out is None:
            continue
        row = {
            'symbol': symbol,
            'event_type': 'RAW_DAILY_SSL_SWEEP_RECLAIM_DEMAND',
            'sweep_date': date_s(b),
            'sweep_idx': i,
            'zone_date': date_s(z),
            'zone_idx': zone_idx,
            'zone_low': round(zone_low, 4),
            'zone_high': round(zone_high, 4),
            'entry_idx': entry_idx,
            'entry_date': date_s(bars[entry_idx]),
            'entry_date_s': date_s(bars[entry_idx]),
            'entry_price': round(entry, 4),
            'risk_pct': round(risk_pct, 4),
            'sweep_depth20_pct': round(sweep_depth20, 4),
            'sweep_close_pos_pct': round(close_pos, 4),
            'sweep_body_pct': round(body_pct, 4),
            'sweep_volr20': round(volr20, 4),
            'prev20_range_pct': round(range20, 4),
            'prev40_range_pct': round(range40, 4),
            'pre20_trend_pct': round(trend20, 4),
            'zone_width_pct': round((zone_high / max(zone_low, 1e-9) - 1) * 100, 4),
            'entry_chase_above_zone_pct': round((entry / max(zone_high, 1e-9) - 1) * 100, 4),
            'no_write': True,
            'production_write': False,
            'frontend_write': False,
            'watchlist_write': False,
        }
        row.update(out)
        rows.append(row)
    return rows


def cut_recent(df: pd.DataFrame) -> pd.DataFrame:
    latest = str(df['entry_date_s'].max())
    cutoff = (datetime.strptime(latest, '%Y%m%d') - timedelta(days=45)).strftime('%Y%m%d')
    return df[df['entry_date_s'] >= cutoff].copy()


def quantile_thresholds(s: pd.Series, qs: list[float]) -> list[float]:
    vals = []
    ser = pd.to_numeric(s, errors='coerce').dropna()
    if len(ser) == 0:
        return vals
    for q in qs:
        vals.append(round(float(ser.quantile(q)), 4))
    return sorted(set(vals))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = add_key(pd.read_csv(BASELINE, low_memory=False))
    baseline_metrics = metrics(baseline)
    rows: list[dict[str, Any]] = []
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    for p in files:
        rows.extend(generate_symbol(p))
    all_df = pd.DataFrame(rows)
    if all_df.empty:
        raise SystemExit('no rows generated')
    all_df = add_key(all_df)
    all_df = all_df.drop_duplicates('_key', keep='first')
    nonoverlap = all_df[~all_df['_key'].isin(set(baseline['_key']))].copy()
    current = cut_recent(all_df)
    current_nonoverlap = current[~current['_key'].isin(set(baseline['_key']))].copy()

    feats = ['risk_pct', 'sweep_depth20_pct', 'sweep_close_pos_pct', 'sweep_body_pct', 'sweep_volr20', 'prev20_range_pct', 'prev40_range_pct', 'pre20_trend_pct', 'zone_width_pct', 'entry_chase_above_zone_pct']
    atomic: list[tuple[str, pd.Series, pd.Series]] = []
    for col in feats:
        qs = [0.2, 0.35, 0.5, 0.65, 0.8]
        for th in quantile_thresholds(nonoverlap[col], qs):
            atomic.append((f'{col} >= {th}', nonoverlap[col] >= th, current_nonoverlap[col] >= th))
            atomic.append((f'{col} <= {th}', nonoverlap[col] <= th, current_nonoverlap[col] <= th))
    # Structural fixed predicates, still pre-entry/source-safe.
    atomic.extend([
        ('sweep_close_pos_pct >= 60', nonoverlap['sweep_close_pos_pct'] >= 60, current_nonoverlap['sweep_close_pos_pct'] >= 60),
        ('sweep_close_pos_pct >= 75', nonoverlap['sweep_close_pos_pct'] >= 75, current_nonoverlap['sweep_close_pos_pct'] >= 75),
        ('sweep_depth20_pct >= 1', nonoverlap['sweep_depth20_pct'] >= 1, current_nonoverlap['sweep_depth20_pct'] >= 1),
        ('sweep_volr20 >= 1.2', nonoverlap['sweep_volr20'] >= 1.2, current_nonoverlap['sweep_volr20'] >= 1.2),
        ('pre20_trend_pct <= 0', nonoverlap['pre20_trend_pct'] <= 0, current_nonoverlap['pre20_trend_pct'] <= 0),
    ])

    viable_atomic = []
    for name, mask, cmask in atomic:
        current_hits = int(cmask.sum())
        child_count = int(mask.sum())
        if current_hits < 5 or child_count < 17:
            continue
        child_m = metrics(nonoverlap.loc[mask[mask].index])
        viable_atomic.append((name, mask, cmask, child_m, current_hits))
    viable_atomic = sorted(
        viable_atomic,
        key=lambda x: (x[3].get('wr', 0), x[3].get('avg', 0), -x[3].get('n', 999999)),
        reverse=True,
    )[:45]

    candidates = []
    tested = 0
    # Keep the probe bounded: all viable single rules + pairwise intersections among
    # the best 45 atomic predicates. This is a source-layer go/no-go screen, not a
    # production optimizer; wide three-way grids would be slow and overfit current rows.
    for r in [1, 2]:
        for combo in combinations(range(len(viable_atomic)), r):
            tested += 1
            names = [viable_atomic[i][0] for i in combo]
            mask = pd.Series(True, index=nonoverlap.index)
            cmask = pd.Series(True, index=current_nonoverlap.index)
            for i in combo:
                mask &= viable_atomic[i][1]
                cmask &= viable_atomic[i][2]
            child_idx = mask[mask].index
            current_hits = int(cmask.sum())
            if current_hits < 5 or len(child_idx) < 10:
                continue
            child = nonoverlap.loc[child_idx].copy()
            child_m = metrics(child)
            # Mathematical pruning: V248 baseline already sits at WR 94.415 / Avg 7.602.
            # A large, low-quality child cannot preserve the combined frontier; avoid
            # expensive combined monthly/yearly metrics for obviously impossible rules.
            if child_m.get('n', 0) < 17 or child_m.get('wr', 0) < 80 or child_m.get('avg', 0) < 5.0:
                continue
            combined = pd.concat([baseline, child], ignore_index=True).drop_duplicates('_key', keep='first')
            cm = metrics(combined)
            candidates.append({
                'rule': ' AND '.join(names),
                'pred_count': r,
                'current_recent45_hits': current_hits,
                'child_n': child_m.get('n', 0),
                'child_wr': child_m.get('wr', 0),
                'child_avg': child_m.get('avg', 0),
                'child_min_year_n': child_m.get('min_year_n', 0),
                'combined_n': cm.get('n', 0),
                'combined_wr': cm.get('wr', 0),
                'combined_avg': cm.get('avg', 0),
                'combined_min_year_n': cm.get('min_year_n', 0),
                'combined_all_year_wr_min': cm.get('all_year_wr_min', 0),
                'combined_micro': cm.get('micro', 99),
                'combined_weak_month_count': cm.get('weak_month_count', 99),
                'combined_prod_pass': pass_gate(cm, PROD),
                'combined_research_pass': pass_gate(cm, RESEARCH),
            })
    candidates = sorted(candidates, key=lambda x: (x['combined_prod_pass'], x['combined_research_pass'], x['combined_wr'], x['combined_avg'], x['current_recent45_hits']), reverse=True)
    frontier = pd.DataFrame(candidates)
    all_df.to_csv(OUT / 'v264_all_sweep_reclaim_candidates.csv', index=False)
    current_nonoverlap.to_csv(OUT / 'v264_current_recent45_candidates.csv', index=False)
    frontier.to_csv(OUT / 'v264_frontier.csv', index=False)
    summary = {
        'version': 'V264_LIQUIDITY_SWEEP_RECLAIM_SOURCE_PROBE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'inputs': {'baseline': str(BASELINE), 'kline_dir': str(KLINE_DIR), 'kline_files': len(files)},
        'gates': {'production': PROD, 'research': RESEARCH},
        'baseline_metrics': baseline_metrics,
        'generated': {
            'all_candidates': int(len(all_df)),
            'historical_nonoverlap_vs_baseline': int(len(nonoverlap)),
            'current_recent45_candidates': int(len(current)),
            'current_recent45_nonoverlap': int(len(current_nonoverlap)),
            'latest_entry_date': str(all_df['entry_date_s'].max()),
        },
        'raw_generator_metrics': {'child': metrics(nonoverlap), 'combined': metrics(pd.concat([baseline, nonoverlap], ignore_index=True).drop_duplicates('_key', keep='first'))},
        'rules_tested': tested,
        'production_pass_count': int(sum(1 for x in candidates if x['combined_prod_pass'])),
        'research_pass_count': int(sum(1 for x in candidates if x['combined_research_pass'])),
        'top_candidates': candidates[:20],
        'decision': 'NO_PROMOTION__PENDING_GATE_RESULT' if not candidates else ('PROMOTION_CANDIDATE_FOUND_NEEDS_INDEPENDENT_AUDIT' if candidates[0]['combined_prod_pass'] else 'NO_PROMOTION__RAW_SSL_SWEEP_RECLAIM_DOES_NOT_PASS_GATES'),
    }
    (OUT / 'v264_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({
        'latest': str(LATEST),
        'out_dir': str(OUT),
        'generated': summary['generated'],
        'production_pass_count': summary['production_pass_count'],
        'research_pass_count': summary['research_pass_count'],
        'best': summary['top_candidates'][0] if summary['top_candidates'] else None,
        'decision': summary['decision'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
