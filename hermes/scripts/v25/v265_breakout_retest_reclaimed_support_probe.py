#!/usr/bin/env python3
"""V265 no-write: raw daily breakout-retest reclaimed-support source-layer probe.

New source family after V262/V264 failed:
  1) A bullish event closes above prior 20/40-day high (true BOS/breakout).
  2) Price retests the reclaimed prior-high level within 8 bars and closes back above it.
  3) Entry is next open after the retest/reclaim candle.
  4) Selector fields use only bars up to the retest/reclaim candle plus entry open.

Research only. No production/frontend/watchlist writes.
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
OUT = BASE / f'smc_audit/v265_breakout_retest_reclaimed_support_no_write_{TS}'
LATEST = BASE / 'smc_audit/v265_breakout_retest_reclaimed_support_latest.json'

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
        'hold_bars': int(exit_idx - entry_idx),
        't1_violation': date_s(bars[exit_idx]) == date_s(bars[entry_idx]),
    }


def scan_symbol(path: Path) -> list[dict[str, Any]]:
    symbol = symbol_from_path(path)
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    if len(bars) < 90:
        return rows
    for event_idx in range(45, len(bars) - 11):
        b = bars[event_idx]
        o = fnum(b['o']); h = fnum(b['h']); l = fnum(b['l']); c = fnum(b['c']); v = fnum(b.get('v'))
        if min(o, h, l, c) <= 0 or h <= l or c <= o:
            continue
        prev20 = bars[event_idx - 20:event_idx]
        prev40 = bars[event_idx - 40:event_idx]
        prev20_high = max(fnum(x['h']) for x in prev20)
        prev20_low = min(fnum(x['l']) for x in prev20)
        prev40_high = max(fnum(x['h']) for x in prev40)
        prev40_low = min(fnum(x['l']) for x in prev40)
        break20 = (c / max(prev20_high, 1e-9) - 1) * 100
        break40 = (c / max(prev40_high, 1e-9) - 1) * 100
        if break20 <= 0 or break40 <= -0.5:
            continue
        body_pct = abs(c - o) / max(h - l, 1e-9) * 100
        close_pos = (c - l) / max(h - l, 1e-9) * 100
        volr20 = v / max(sum(fnum(x.get('v')) for x in prev20) / 20, 1e-9)
        prev20_range = (prev20_high / max(prev20_low, 1e-9) - 1) * 100
        prev40_range = (prev40_high / max(prev40_low, 1e-9) - 1) * 100
        pre20_trend = (fnum(bars[event_idx - 1]['c']) / max(fnum(bars[event_idx - 20]['c']), 1e-9) - 1) * 100
        level = prev20_high
        for retest_idx in range(event_idx + 1, min(event_idx + 9, len(bars) - 1)):
            r = bars[retest_idx]
            ro = fnum(r['o']); rh = fnum(r['h']); rl = fnum(r['l']); rc = fnum(r['c']); rv = fnum(r.get('v'))
            if min(ro, rh, rl, rc) <= 0 or rh <= rl:
                continue
            touched = rl <= level * 1.018
            held = rc >= level * 0.995 and rc > ro and (rc - rl) / max(rh - rl, 1e-9) >= 0.55
            if not (touched and held):
                continue
            entry_idx = retest_idx + 1
            entry = fnum(bars[entry_idx]['o'])
            # Structural stop: below retest wick and reclaimed support, whichever is lower, with buffer.
            sl = min(rl, level * 0.985) * 0.99
            risk_pct = (entry / max(sl, 1e-9) - 1) * 100
            if not (0.8 <= risk_pct <= 14.0):
                continue
            out = replay_exit(bars, entry_idx, entry, sl)
            if out is None:
                continue
            retest_depth = (level / max(rl, 1e-9) - 1) * 100
            retest_reclaim_margin = (rc / max(level, 1e-9) - 1) * 100
            retest_body_pct = abs(rc - ro) / max(rh - rl, 1e-9) * 100
            retest_close_pos = (rc - rl) / max(rh - rl, 1e-9) * 100
            rows.append({
                'symbol': symbol,
                'event_type': 'RAW_DAILY_BREAKOUT_RETEST_RECLAIMED_SUPPORT',
                'event_date': date_s(b),
                'event_idx': event_idx,
                'level_price': round(level, 4),
                'retest_date': date_s(r),
                'retest_idx': retest_idx,
                'entry_idx': entry_idx,
                'entry_date': date_s(bars[entry_idx]),
                'entry_date_s': date_s(bars[entry_idx]),
                'entry_price': round(entry, 4),
                'sl': round(sl, 4),
                'risk_pct': round(risk_pct, 4),
                'event_break20_pct': round(break20, 4),
                'event_break40_pct': round(break40, 4),
                'event_body_pct': round(body_pct, 4),
                'event_close_pos_pct': round(close_pos, 4),
                'event_volr20': round(volr20, 4),
                'prev20_range_pct': round(prev20_range, 4),
                'prev40_range_pct': round(prev40_range, 4),
                'pre20_trend_pct': round(pre20_trend, 4),
                'event_to_retest_bars': retest_idx - event_idx,
                'retest_depth_pct': round(retest_depth, 4),
                'retest_reclaim_margin_pct': round(retest_reclaim_margin, 4),
                'retest_body_pct': round(retest_body_pct, 4),
                'retest_close_pos_pct': round(retest_close_pos, 4),
                'retest_volr20': round(rv / max(sum(fnum(x.get('v')) for x in bars[retest_idx-20:retest_idx]) / 20, 1e-9), 4),
                'entry_chase_above_level_pct': round((entry / max(level, 1e-9) - 1) * 100, 4),
                'no_write': True,
                'production_write': False,
                'frontend_write': False,
                'watchlist_write': False,
                **out,
            })
            break
    return rows


def cut_recent(df: pd.DataFrame) -> pd.DataFrame:
    latest = str(df['entry_date_s'].max())
    cutoff = (datetime.strptime(latest, '%Y%m%d') - timedelta(days=45)).strftime('%Y%m%d')
    return df[df['entry_date_s'] >= cutoff].copy()


def qths(s: pd.Series, qs: list[float]) -> list[float]:
    ser = pd.to_numeric(s, errors='coerce').dropna()
    return sorted(set(round(float(ser.quantile(q)), 4) for q in qs)) if len(ser) else []


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = add_key(pd.read_csv(BASELINE, low_memory=False))
    baseline_metrics = metrics(baseline)
    rows: list[dict[str, Any]] = []
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    for p in files:
        rows.extend(scan_symbol(p))
    all_df = pd.DataFrame(rows)
    if all_df.empty:
        raise SystemExit('no rows generated')
    all_df = add_key(all_df).drop_duplicates('_key', keep='first')
    nonoverlap = all_df[~all_df['_key'].isin(set(baseline['_key']))].copy()
    current = cut_recent(all_df)
    current_nonoverlap = current[~current['_key'].isin(set(baseline['_key']))].copy()

    feats = [
        'risk_pct', 'event_break20_pct', 'event_break40_pct', 'event_body_pct', 'event_close_pos_pct', 'event_volr20',
        'prev20_range_pct', 'prev40_range_pct', 'pre20_trend_pct', 'event_to_retest_bars', 'retest_depth_pct',
        'retest_reclaim_margin_pct', 'retest_body_pct', 'retest_close_pos_pct', 'retest_volr20', 'entry_chase_above_level_pct'
    ]
    atomic: list[tuple[str, pd.Series, pd.Series]] = []
    for col in feats:
        for th in qths(nonoverlap[col], [0.2, 0.35, 0.5, 0.65, 0.8]):
            atomic.append((f'{col} >= {th}', nonoverlap[col] >= th, current_nonoverlap[col] >= th))
            atomic.append((f'{col} <= {th}', nonoverlap[col] <= th, current_nonoverlap[col] <= th))
    atomic.extend([
        ('event_body_pct >= 60', nonoverlap['event_body_pct'] >= 60, current_nonoverlap['event_body_pct'] >= 60),
        ('event_close_pos_pct >= 70', nonoverlap['event_close_pos_pct'] >= 70, current_nonoverlap['event_close_pos_pct'] >= 70),
        ('event_volr20 >= 1.2', nonoverlap['event_volr20'] >= 1.2, current_nonoverlap['event_volr20'] >= 1.2),
        ('retest_close_pos_pct >= 70', nonoverlap['retest_close_pos_pct'] >= 70, current_nonoverlap['retest_close_pos_pct'] >= 70),
        ('event_to_retest_bars <= 3', nonoverlap['event_to_retest_bars'] <= 3, current_nonoverlap['event_to_retest_bars'] <= 3),
        ('entry_chase_above_level_pct <= 3', nonoverlap['entry_chase_above_level_pct'] <= 3, current_nonoverlap['entry_chase_above_level_pct'] <= 3),
    ])

    viable = []
    for name, mask, cmask in atomic:
        current_hits = int(cmask.sum())
        child_count = int(mask.sum())
        if current_hits < 5 or child_count < 17:
            continue
        child_m = metrics(nonoverlap.loc[mask[mask].index])
        viable.append((name, mask, cmask, child_m, current_hits))
    viable = sorted(viable, key=lambda x: (x[3].get('wr', 0), x[3].get('avg', 0), -x[3].get('n', 999999)), reverse=True)[:55]

    candidates = []
    tested = 0
    for r in [1, 2]:
        for combo in combinations(range(len(viable)), r):
            tested += 1
            names = [viable[i][0] for i in combo]
            mask = pd.Series(True, index=nonoverlap.index)
            cmask = pd.Series(True, index=current_nonoverlap.index)
            for i in combo:
                mask &= viable[i][1]
                cmask &= viable[i][2]
            current_hits = int(cmask.sum())
            child_idx = mask[mask].index
            if current_hits < 5 or len(child_idx) < 10:
                continue
            child = nonoverlap.loc[child_idx].copy()
            child_m = metrics(child)
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
    all_df.to_csv(OUT / 'v265_all_breakout_retest_candidates.csv', index=False)
    current_nonoverlap.to_csv(OUT / 'v265_current_recent45_candidates.csv', index=False)
    frontier.to_csv(OUT / 'v265_frontier.csv', index=False)
    summary = {
        'version': 'V265_BREAKOUT_RETEST_RECLAIMED_SUPPORT_NO_WRITE',
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
        'decision': 'NO_PROMOTION__PENDING_GATE_RESULT' if not candidates else ('PROMOTION_CANDIDATE_FOUND_NEEDS_INDEPENDENT_AUDIT' if candidates[0]['combined_prod_pass'] else 'NO_PROMOTION__BREAKOUT_RETEST_RECLAIMED_SUPPORT_DOES_NOT_PASS_GATES'),
        'next_research_direction': [
            'If no pass: daily breakout-retest/reclaimed-support has current supply but cannot preserve V248 historical frontier under source-safe rules.',
            'Next valid direction is not scalar pruning this family; test a materially different source such as pre-entry intraday/auction/turnover-quality or industry-flow data if available.'
        ],
    }
    (OUT / 'v265_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({
        'latest': str(LATEST),
        'out_dir': str(OUT),
        'generated': summary['generated'],
        'raw_child': summary['raw_generator_metrics']['child'],
        'production_pass_count': summary['production_pass_count'],
        'research_pass_count': summary['research_pass_count'],
        'best': summary['top_candidates'][0] if summary['top_candidates'] else None,
        'decision': summary['decision'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
