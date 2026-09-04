#!/usr/bin/env python3
"""V271 no-write: time-ordered SMC sequence parameter surface probe.

Goal: explain low trade volume from the chronological-combo layer, assuming
primitive SMC indicators are acceptable. This does not write production,
frontend, or watchlist state.

Sequence under test:
  BOS_UP -> nearest prior bearish demand candle -> later zone touch/reclaim -> next-open entry.

Compared parameters:
  - BOS lookback: 10/20/40 prior highs
  - Demand search lookback before BOS: 3/5/8/12 bars
  - Retest wait after BOS: 3/5/8/12/20 bars
  - Reclaim strictness: strict_v262 / soft_mid / touch_bull / support_hold
  - Optional prior SSL event within 10/20/40 bars before BOS (diagnostic only)

All selector fields use only bars <= reclaim_idx; exit replay starts T+1.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KLINE_DIR = BASE / 'kline_cache'
BASELINE = BASE / 'smc_audit/v248_v246_independent_audit_no_write_20260701_172916/v248_recomputed_selected_rows.csv'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v271_time_order_parameter_surface_no_write_{TS}'
LATEST = BASE / 'smc_audit/v271_time_order_parameter_surface_latest.json'

BOS_LOOKBACKS = [10, 20, 40]
DEMAND_LOOKBACKS = [3, 5, 8, 12]
WAIT_MAXES = [3, 5, 8, 12, 20]
RECLAIM_MODES = ['strict_v262', 'soft_mid', 'touch_bull', 'support_hold']
SSL_WINDOWS = [10, 20, 40]

PROD = dict(n=600, min_year_n=70, wr=94.0, avg=7.6, year_wr_min=92.0, micro=1.0, weak_month_count=6, t1=0)
RESEARCH = dict(n=590, min_year_n=70, wr=93.5, avg=7.5, year_wr_min=91.0, micro=1.0, weak_month_count=8, t1=0)


def fnum(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
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
    if df.empty:
        return {'n': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    ok = pnl.notna()
    df = df[ok].copy()
    pnl = pnl[ok]
    if df.empty:
        return {'n': 0}
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
    exit_price = fnum(bars[last].get('c'))
    reason = f'TIME{max_hold}'
    for i in range(first_exit, last + 1):
        lo = fnum(bars[i].get('l'))
        hi = fnum(bars[i].get('h'))
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


def has_prior_ssl(bars: list[dict[str, Any]], event_idx: int, window: int, ssl_lb: int = 20) -> bool:
    start = max(ssl_lb, event_idx - window)
    for i in range(start, event_idx):
        prev = bars[i - ssl_lb:i]
        if not prev:
            continue
        prior_low = min(fnum(x.get('l')) for x in prev)
        lo = fnum(bars[i].get('l'))
        close = fnum(bars[i].get('c'))
        if lo < prior_low and close > prior_low:
            return True
    return False


def reclaim_ok(mode: str, rb: dict[str, Any], dz_low: float, dz_high: float) -> bool:
    ro = fnum(rb.get('o')); rc = fnum(rb.get('c')); rh = fnum(rb.get('h')); rl = fnum(rb.get('l'))
    rng = max(rh - rl, 1e-9)
    touched = rl <= dz_high * 1.005
    if not touched:
        return False
    if mode == 'strict_v262':
        return rc >= dz_high and rc > ro and (rc - rl) / rng >= 0.55
    if mode == 'soft_mid':
        return rc >= (dz_low + dz_high) / 2 and (rc - rl) / rng >= 0.45
    if mode == 'touch_bull':
        return rc > ro and rc >= dz_low
    if mode == 'support_hold':
        return rc >= dz_low
    raise ValueError(mode)


def scan_symbol(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    symbol = symbol_from_path(path)
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return [], {'symbol': symbol, 'error': 'json_read_failed'}
    if len(bars) < 90:
        return [], {'symbol': symbol, 'error': 'too_few_bars'}

    rows: list[dict[str, Any]] = []
    funnel = Counter()
    variant_funnel = Counter()

    for event_idx in range(max(BOS_LOOKBACKS), len(bars) - 2):
        event = bars[event_idx]
        o = fnum(event.get('o')); c = fnum(event.get('c')); h = fnum(event.get('h')); l = fnum(event.get('l')); v = fnum(event.get('v'))
        if h <= l or c <= o:
            continue
        for bos_lb in BOS_LOOKBACKS:
            prev = bars[event_idx - bos_lb:event_idx]
            prev_high = max(fnum(x.get('h')) for x in prev)
            prev_low = min(fnum(x.get('l')) for x in prev)
            break_pct = (c / max(prev_high, 1e-9) - 1) * 100
            if break_pct <= 0:
                continue
            funnel[(bos_lb, 'bos')] += 1
            prev_range = (prev_high / max(prev_low, 1e-9) - 1) * 100
            body = abs(c - o) / max(h - l, 1e-9) * 100
            close_pos = (c - l) / max(h - l, 1e-9) * 100
            volr = v / max(sum(fnum(x.get('v')) for x in prev) / len(prev), 1e-9)
            prior_ssl = {f'prior_ssl_{w}': has_prior_ssl(bars, event_idx, w) for w in SSL_WINDOWS}

            for demand_lb in DEMAND_LOOKBACKS:
                demand_i = None
                for k in range(event_idx - 1, max(event_idx - demand_lb - 1, -1), -1):
                    if fnum(bars[k].get('c')) < fnum(bars[k].get('o')):
                        demand_i = k
                        break
                variant_base = (bos_lb, demand_lb)
                if demand_i is None:
                    continue
                funnel[(bos_lb, f'zone_found_lb{demand_lb}')] += 1
                dz_low = fnum(bars[demand_i].get('l'))
                dz_high = max(fnum(bars[demand_i].get('o')), fnum(bars[demand_i].get('c')))
                if dz_low <= 0 or dz_high <= dz_low:
                    continue
                zone_width = (dz_high / dz_low - 1) * 100

                # Find first reclaim per wait/mode; a stricter wait may be a prefix of broader waits.
                for wait_max in WAIT_MAXES:
                    last_reclaim = min(event_idx + wait_max, len(bars) - 2)
                    touched_any = False
                    for mode in RECLAIM_MODES:
                        found = None
                        for reclaim_idx in range(event_idx + 1, last_reclaim + 1):
                            rb = bars[reclaim_idx]
                            if fnum(rb.get('l')) <= dz_high * 1.005:
                                touched_any = True
                            if reclaim_ok(mode, rb, dz_low, dz_high):
                                found = reclaim_idx
                                break
                        if touched_any:
                            variant_funnel[(bos_lb, demand_lb, wait_max, mode, 'touch')] += 1
                        if found is None:
                            continue
                        variant_funnel[(bos_lb, demand_lb, wait_max, mode, 'reclaim')] += 1
                        entry_idx = found + 1
                        entry = fnum(bars[entry_idx].get('o'))
                        sl = dz_low * 0.99
                        risk = (entry / sl - 1) * 100
                        chase = (entry / max(dz_high, 1e-9) - 1) * 100
                        if not (0.8 <= risk <= 12.0):
                            continue
                        variant_funnel[(bos_lb, demand_lb, wait_max, mode, 'risk_ok')] += 1
                        ex = replay_exit(bars, entry_idx, entry, sl)
                        if ex is None:
                            continue
                        rows.append({
                            'symbol': symbol,
                            'event_type': 'BOS_DEMAND_RETEST_PARAM_SURFACE',
                            'bos_lookback': bos_lb,
                            'demand_lookback': demand_lb,
                            'wait_max': wait_max,
                            'reclaim_mode': mode,
                            'event_date': date_s(event),
                            'event_idx': event_idx,
                            'zone_date': date_s(bars[demand_i]),
                            'zone_idx': demand_i,
                            'zone_low': round(dz_low, 4),
                            'zone_high': round(dz_high, 4),
                            'reclaim_date': date_s(bars[found]),
                            'reclaim_idx': found,
                            'entry_idx': entry_idx,
                            'entry_date': date_s(bars[entry_idx]),
                            'entry_date_s': date_s(bars[entry_idx]),
                            'entry_price': round(entry, 4),
                            'risk_pct': round(risk, 4),
                            'entry_chase_above_zone_pct': round(chase, 4),
                            'raw_event_break_pct': round(break_pct, 4),
                            'raw_event_body_pct': round(body, 4),
                            'raw_event_close_pos_pct': round(close_pos, 4),
                            'raw_event_volr': round(volr, 4),
                            'raw_prev_range_pct': round(prev_range, 4),
                            'zone_width_pct': round(zone_width, 4),
                            'event_to_reclaim_bars': found - event_idx,
                            'no_write': True,
                            'production_write': False,
                            'frontend_write': False,
                            'watchlist_write': False,
                            **prior_ssl,
                            **ex,
                        })
    summary = {
        'symbol': symbol,
        'bars': len(bars),
        'funnel': {str(k): int(v) for k, v in funnel.items()},
        'variant_funnel': {str(k): int(v) for k, v in variant_funnel.items()},
    }
    return rows, summary


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(KLINE_DIR.glob('*_daily_750.json'))
    baseline = add_key(pd.read_csv(BASELINE, low_memory=False)) if BASELINE.exists() else pd.DataFrame()

    all_rows: list[dict[str, Any]] = []
    symbol_summaries = []
    for idx, p in enumerate(paths, 1):
        rows, summary = scan_symbol(p)
        all_rows.extend(rows)
        symbol_summaries.append(summary)
        if idx % 500 == 0:
            print(f'scanned {idx}/{len(paths)} files rows={len(all_rows)}', flush=True)

    if not all_rows:
        raise SystemExit('no rows generated')
    df = pd.DataFrame(all_rows)
    df['_key_variant'] = (
        df['symbol'].astype(str) + '|' + df['entry_date_s'].astype(str) + '|'
        + df['bos_lookback'].astype(str) + '|' + df['demand_lookback'].astype(str) + '|'
        + df['wait_max'].astype(str) + '|' + df['reclaim_mode'].astype(str)
    )
    df = df.drop_duplicates('_key_variant', keep='first')
    df['_key'] = df['symbol'].astype(str) + '|' + df['entry_date_s'].astype(str)
    latest_dt = max(pd.to_datetime(df['entry_date_s'], format='%Y%m%d', errors='coerce').dropna())
    cutoff = (latest_dt - timedelta(days=45)).strftime('%Y%m%d')

    # Per variant: dedupe same symbol/date inside the variant. Compare raw volume, quality, and current hits.
    variant_rows = []
    for (bos_lb, demand_lb, wait_max, mode), g in df.groupby(['bos_lookback', 'demand_lookback', 'wait_max', 'reclaim_mode']):
        g = g.drop_duplicates('_key', keep='first').copy()
        m = metrics(g)
        current_hits = int((g['entry_date_s'].astype(str) >= cutoff).sum())
        per_stock_3y = round(len(g) / max(len(paths), 1), 3)
        variant_rows.append({
            'bos_lookback': int(bos_lb),
            'demand_lookback': int(demand_lb),
            'wait_max': int(wait_max),
            'reclaim_mode': str(mode),
            'n': m.get('n', 0),
            'wr': m.get('wr', 0),
            'avg': m.get('avg', 0),
            'median': m.get('median', 0),
            'min_year_n': m.get('min_year_n', 0),
            'all_year_wr_min': m.get('all_year_wr_min', 0),
            'micro': m.get('micro', 99),
            'weak_month_count': m.get('weak_month_count', 99),
            'loss': m.get('loss', 0),
            'current_recent45_hits': current_hits,
            'per_stock_3y': per_stock_3y,
            'per_stock_per_year': round(per_stock_3y / 3.0, 3),
            'prod_pass': pass_gate(m, PROD),
            'research_pass': pass_gate(m, RESEARCH),
            'year_counts': json.dumps(m.get('year_counts', {}), ensure_ascii=False),
            'year_wr': json.dumps(m.get('year_wr', {}), ensure_ascii=False),
        })
    vf = pd.DataFrame(variant_rows).sort_values(
        ['prod_pass', 'research_pass', 'wr', 'avg', 'current_recent45_hits'],
        ascending=[False, False, False, False, False],
    )

    # Sequence diagnostics: prior SSL as a time-ordered prerequisite usually lowers volume; quantify by variant-independent row set.
    ssl_diag = []
    base_dedup = df.drop_duplicates('_key', keep='first').copy()
    for col in [f'prior_ssl_{w}' for w in SSL_WINDOWS]:
        for flag, g in base_dedup.groupby(col):
            m = metrics(g)
            ssl_diag.append({'predicate': f'{col}={bool(flag)}', **m, 'current_recent45_hits': int((g['entry_date_s'].astype(str) >= cutoff).sum())})

    # Funnel aggregation by symbol summaries.
    funnel_total = Counter()
    variant_funnel_total = Counter()
    for s in symbol_summaries:
        for k, v in s.get('funnel', {}).items():
            funnel_total[k] += int(v)
        for k, v in s.get('variant_funnel', {}).items():
            variant_funnel_total[k] += int(v)

    top_volume = vf.sort_values(['n', 'wr', 'avg'], ascending=[False, False, False]).head(20).to_dict('records')
    top_quality = vf.head(30).to_dict('records')
    mode_summary = []
    for mode, g in vf.groupby('reclaim_mode'):
        mode_summary.append({
            'reclaim_mode': mode,
            'best_wr': round(float(g['wr'].max()), 4),
            'best_avg': round(float(g.sort_values('wr', ascending=False).iloc[0]['avg']), 4),
            'max_n': int(g['n'].max()),
            'best_current_hits': int(g.sort_values('wr', ascending=False).iloc[0]['current_recent45_hits']),
        })

    df.to_csv(OUT / 'v271_all_variant_rows.csv', index=False)
    vf.to_csv(OUT / 'v271_variant_surface.csv', index=False)
    pd.DataFrame(ssl_diag).to_csv(OUT / 'v271_prior_ssl_diagnostic.csv', index=False)
    pd.DataFrame(symbol_summaries).to_json(OUT / 'v271_symbol_funnels.json', orient='records', force_ascii=False, indent=2)

    summary = {
        'version': 'V271_TIME_ORDER_PARAMETER_SURFACE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'inputs': {'kline_dir': str(KLINE_DIR), 'kline_files': len(paths), 'baseline': str(BASELINE)},
        'latest_entry_date': latest_dt.strftime('%Y%m%d'),
        'current_cutoff': cutoff,
        'total_variant_rows': int(len(df)),
        'unique_symbol_entry_dates': int(df['_key'].nunique()),
        'variant_count': int(len(vf)),
        'prod_pass_variants': int(vf['prod_pass'].sum()),
        'research_pass_variants': int(vf['research_pass'].sum()),
        'top_quality': top_quality,
        'top_volume': top_volume,
        'reclaim_mode_summary': sorted(mode_summary, key=lambda x: x['best_wr'], reverse=True),
        'prior_ssl_diagnostic': ssl_diag,
        'funnel_total_sample': dict(funnel_total.most_common(30)),
        'variant_funnel_total_sample': dict(variant_funnel_total.most_common(30)),
        'artifacts': {
            'all_rows': str(OUT / 'v271_all_variant_rows.csv'),
            'variant_surface': str(OUT / 'v271_variant_surface.csv'),
            'prior_ssl_diagnostic': str(OUT / 'v271_prior_ssl_diagnostic.csv'),
            'symbol_funnels': str(OUT / 'v271_symbol_funnels.json'),
        },
    }
    (OUT / 'v271_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:6000])


if __name__ == '__main__':
    main()
