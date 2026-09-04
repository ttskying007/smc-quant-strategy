#!/usr/bin/env python3
"""V262 no-write: fresh BOS continuation -> demand retest generator.

This is a new source-layer probe, not a filter over V128/V230 current rows.
It scans raw daily K-line cache for a source-safe continuation event:
  1) BOS/impulse candle closes above prior-20 high.
  2) Prior-20 structure has sufficient range/energy.
  3) A recent pre-event bearish candle defines demand.
  4) Price retests/reclaims the demand zone before entry.
  5) Entry is next open after reclaim; no entry-day high/low/close in selector.

All outputs are no-write research artifacts.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KLINE_DIR = BASE / 'kline_cache'
BASELINE = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v262_fresh_bos_retest_generator_no_write_{TS}'
LATEST = BASE / 'smc_audit/v262_fresh_bos_retest_generator_latest.json'

PROD = dict(n=600, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=6, t1=0)
RESEARCH = dict(n=590, min_year_n=70, wr=93.5, avg=7.5, year_wr_min=91.0, micro=1.0, weak_month_count=8, t1=0)


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def date_s(bar: dict[str, Any]) -> str:
    return str(bar.get('t', bar.get('date', ''))).replace('.0', '')


def symbol_from_path(path: Path) -> str:
    stem = path.stem.replace('_daily_750', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


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
    # T+1: first executable exit is the bar after entry day.
    first_exit = entry_idx + 1
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
        'hold_bars': exit_idx - entry_idx,
        't1_violation': date_s(bars[exit_idx]) == date_s(bars[entry_idx]),
    }


def scan_symbol(path: Path) -> list[dict[str, Any]]:
    symbol = symbol_from_path(path)
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    if len(bars) < 80:
        return out
    for event_idx in range(25, len(bars) - 2):
        event = bars[event_idx]
        o = fnum(event['o']); c = fnum(event['c']); h = fnum(event['h']); l = fnum(event['l']); v = fnum(event.get('v'))
        if c <= o or h <= l:
            continue
        prev20 = bars[event_idx - 20:event_idx]
        prev10 = bars[event_idx - 10:event_idx]
        prev_high = max(fnum(x['h']) for x in prev20)
        prev_low = min(fnum(x['l']) for x in prev20)
        prev_range = (prev_high / max(prev_low, 1e-9) - 1) * 100
        break20 = (c / max(prev_high, 1e-9) - 1) * 100
        body = abs(c - o) / max(h - l, 1e-9) * 100
        close_pos = (c - l) / max(h - l, 1e-9) * 100
        volr = v / max(sum(fnum(x.get('v')) for x in prev20) / len(prev20), 1e-9)
        # Hard BOS requirement: event close must break the prior-20 high.
        # Threshold search may tighten it, but the raw generator itself must not
        # include ordinary bullish candles.
        if break20 <= 0:
            continue
        # nearest pre-event bearish candle as demand; source-safe and local.
        demand_i = None
        for k in range(event_idx - 1, max(event_idx - 9, -1), -1):
            if fnum(bars[k]['c']) < fnum(bars[k]['o']):
                demand_i = k
                break
        if demand_i is None:
            continue
        dz_low = fnum(bars[demand_i]['l'])
        dz_high = max(fnum(bars[demand_i]['o']), fnum(bars[demand_i]['c']))
        zone_width = (dz_high / max(dz_low, 1e-9) - 1) * 100
        if dz_low <= 0 or zone_width <= 0:
            continue
        # Wait for retest/reclaim. Entry next open after reclaim, so selector does not use entry-day H/L/C.
        for reclaim_idx in range(event_idx + 1, min(event_idx + 8, len(bars) - 1)):
            rb = bars[reclaim_idx]
            ro = fnum(rb['o']); rc = fnum(rb['c']); rh = fnum(rb['h']); rl = fnum(rb['l'])
            touched = rl <= dz_high * 1.005
            reclaimed = rc >= dz_high and rc > ro and (rc - rl) / max(rh - rl, 1e-9) >= 0.55
            if not (touched and reclaimed):
                continue
            entry_idx = reclaim_idx + 1
            entry = fnum(bars[entry_idx]['o'])
            sl = dz_low * 0.99
            risk = (entry / sl - 1) * 100
            chase = (entry / max(dz_high, 1e-9) - 1) * 100
            if not (0.8 <= risk <= 12.0):
                continue
            ex = replay_exit(bars, entry_idx, entry, sl)
            if ex is None:
                # Keep current/incomplete candidate but not historical metric row.
                ex = {'exit_idx': None, 'exit_date': None, 'exit_price': None, 'exit_reason': 'OPEN', 'tp': round(entry + (entry - sl) * 1.5, 4), 'sl': round(sl, 4), 'pnl_pct': None, 'hold_bars': None, 't1_violation': False}
            out.append({
                'symbol': symbol,
                'event_type': 'FRESH_BOS_CONTINUATION_DEMAND_RETEST',
                'event_date': date_s(event),
                'event_idx': event_idx,
                'zone_date': date_s(bars[demand_i]),
                'zone_idx': demand_i,
                'zone_low': round(dz_low, 4),
                'zone_high': round(dz_high, 4),
                'reclaim_date': date_s(rb),
                'reclaim_idx': reclaim_idx,
                'entry_idx': entry_idx,
                'entry_date': date_s(bars[entry_idx]),
                'entry_date_s': date_s(bars[entry_idx]),
                'entry_price': round(entry, 4),
                'risk_pct': round(risk, 4),
                'entry_chase_above_zone_pct': round(chase, 4),
                'raw_event_break20_pct': round(break20, 4),
                'raw_event_body_pct': round(body, 4),
                'raw_event_close_pos_pct': round(close_pos, 4),
                'raw_event_volr': round(volr, 4),
                'raw_prev20_range_pct': round(prev_range, 4),
                'raw_prev10_range_pct': round((max(fnum(x['h']) for x in prev10) / max(min(fnum(x['l']) for x in prev10), 1e-9) - 1) * 100, 4),
                'zone_width_pct': round(zone_width, 4),
                'event_to_reclaim_bars': reclaim_idx - event_idx,
                'no_write': True,
                'production_write': False,
                'frontend_write': False,
                'watchlist_write': False,
                **ex,
            })
            break
    return out


def quantile_thresholds(s: pd.Series, qs: list[float], decimals: int = 4) -> list[float]:
    vals = []
    num = pd.to_numeric(s, errors='coerce').dropna()
    for q in qs:
        if not num.empty:
            vals.append(round(float(num.quantile(q)), decimals))
    return sorted(set(vals))


def apply_rule(df: pd.DataFrame, rule: dict[str, Any]) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for col, op, val in rule['predicates']:
        x = pd.to_numeric(df[col], errors='coerce')
        if op == '>=':
            m &= x >= val
        elif op == '<=':
            m &= x <= val
    return m


def rule_text(rule: dict[str, Any]) -> str:
    return ' AND '.join(f'{c} {op} {v}' for c, op, v in rule['predicates'])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = add_key(pd.read_csv(BASELINE, low_memory=False))
    base_metrics = metrics(baseline)
    paths = sorted(KLINE_DIR.glob('*_daily_750.json'))
    rows: list[dict[str, Any]] = []
    for p in paths:
        rows.extend(scan_symbol(p))
    all_df = pd.DataFrame(rows)
    if all_df.empty:
        raise SystemExit('no candidates generated')
    all_df['_key'] = all_df['symbol'].astype(str) + '|' + all_df['entry_date_s'].astype(str)
    all_df = all_df.drop_duplicates('_key', keep='first')
    latest_date = max(pd.to_datetime(all_df['entry_date_s'], format='%Y%m%d', errors='coerce').dropna())
    cutoff = (latest_date - timedelta(days=45)).strftime('%Y%m%d')
    hist = all_df[all_df['pnl_pct'].notna()].copy()
    current = all_df[all_df['entry_date_s'].astype(str) >= cutoff].copy()
    nonoverlap = hist[~hist['_key'].isin(set(baseline['_key']))].copy()

    # Source-safe threshold search. Current hits are measured on the fresh generator itself.
    thresholds = {
        'raw_prev20_range_pct': quantile_thresholds(nonoverlap['raw_prev20_range_pct'], [0.25, 0.5, 0.65, 0.75]),
        'raw_event_body_pct': quantile_thresholds(nonoverlap['raw_event_body_pct'], [0.5, 0.65, 0.75]),
        'raw_event_break20_pct': quantile_thresholds(nonoverlap['raw_event_break20_pct'], [0.25, 0.5, 0.65]),
        'risk_pct': quantile_thresholds(nonoverlap['risk_pct'], [0.35, 0.5, 0.65]),
        'entry_chase_above_zone_pct': quantile_thresholds(nonoverlap['entry_chase_above_zone_pct'], [0.35, 0.5, 0.65]),
        'event_to_reclaim_bars': [2, 3, 5],
    }
    atoms: list[tuple[str, str, float]] = []
    for col, vals in thresholds.items():
        for v in vals:
            atoms.append((col, '<=' if col in {'risk_pct', 'entry_chase_above_zone_pct', 'event_to_reclaim_bars'} else '>=', v))

    frontier = []
    # Single and paired predicates only: enough to test direction without overfitting.
    combos = [(a,) for a in atoms] + [pair for pair in product(atoms, atoms) if pair[0] < pair[1] and pair[0][0] != pair[1][0]]
    for preds in combos:
        rule = {'predicates': list(preds)}
        child = nonoverlap[apply_rule(nonoverlap, rule)].copy()
        if len(child) < 20:
            continue
        combined = pd.concat([baseline, child], ignore_index=True, sort=False).drop_duplicates('_key', keep='first')
        cm = metrics(combined)
        hm = metrics(child)
        cur_hits = int(apply_rule(current, rule).sum()) if not current.empty else 0
        frontier.append({
            'rule': rule_text(rule),
            'pred_count': len(preds),
            'current_recent45_hits': cur_hits,
            'child_n': hm.get('n', 0),
            'child_wr': hm.get('wr', 0),
            'child_avg': hm.get('avg', 0),
            'child_min_year_n': hm.get('min_year_n', 0),
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
    fr = pd.DataFrame(frontier)
    if fr.empty:
        top = []
        prod_pass = research_pass = 0
    else:
        fr = fr.sort_values(
            ['combined_prod_pass', 'combined_research_pass', 'combined_wr', 'combined_avg', 'current_recent45_hits'],
            ascending=[False, False, False, False, False],
        )
        prod_pass = int(fr['combined_prod_pass'].sum())
        research_pass = int(fr['combined_research_pass'].sum())
        top = fr.head(30).to_dict('records')
        fr.to_csv(OUT / 'v262_frontier.csv', index=False)
    all_df.to_csv(OUT / 'v262_all_fresh_candidates.csv', index=False)
    current.to_csv(OUT / 'v262_current_recent45_candidates.csv', index=False)

    summary = {
        'version': 'V262_FRESH_BOS_RETEST_GENERATOR_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'inputs': {'baseline': str(BASELINE), 'kline_dir': str(KLINE_DIR), 'kline_files': len(paths)},
        'gates': {'production': PROD, 'research': RESEARCH},
        'baseline_metrics': base_metrics,
        'generated': {
            'all_candidates': int(len(all_df)),
            'historical_complete': int(len(hist)),
            'historical_nonoverlap_vs_baseline': int(len(nonoverlap)),
            'current_recent45_candidates': int(len(current)),
            'latest_entry_date': latest_date.strftime('%Y%m%d'),
            'current_cutoff': cutoff,
        },
        'raw_generator_metrics': {
            'child': metrics(nonoverlap),
            'combined_with_baseline': metrics(pd.concat([baseline, nonoverlap], ignore_index=True, sort=False).drop_duplicates('_key', keep='first')),
        },
        'rules_tested': int(len(fr)) if not fr.empty else 0,
        'production_pass_count': prod_pass,
        'research_pass_count': research_pass,
        'top_candidates': top,
        'decision': 'PROMOTABLE_RULE_FOUND__NO_WRITE' if prod_pass else ('RESEARCH_RULE_FOUND__NO_WRITE' if research_pass else 'NO_PROMOTION__FRESH_BOS_RETEST_GENERATOR_DOES_NOT_PASS_GATES'),
        'next_research_direction': [
            'If no pass: the raw daily BOS->demand retest generator creates current rows but lacks historical quality; do not route.',
            'Next valid direction is lower-timeframe confirmation at candidate generation time or a stronger BULL_CONTINUATION environment source, not scalar pruning.',
        ],
    }
    (OUT / 'v262_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
