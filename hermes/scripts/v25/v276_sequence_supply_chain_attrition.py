#!/usr/bin/env python3
"""V276 no-write: SMC chronological sequence supply-chain attrition audit.

Goal: answer why opportunities are still sparse/low-quality if primitive SMC
indicators are assumed correct. This does not tune production. It measures full
market primitive event density and where chronological combinations collapse:
SSL sweep -> demand zone -> bullish BOS -> retest/reclaim -> entry.

Outputs are research artifacts only; no frontend/watchlist/production writes.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE = Path('/root/.hermes')
KDIR = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v276_sequence_supply_chain_attrition_no_write_{TS}'
LATEST = BASE / 'smc_audit/v276_sequence_supply_chain_attrition_latest.json'

YEARS = {'2023', '2024', '2025', '2026'}
BOS_LOOKBACKS = [10, 20, 40]
DEMAND_LOOKBACKS = [3, 5, 8, 12, 20]
SSL_WINDOWS = [0, 5, 10, 20, 40, 80]  # 0 means no SSL requirement
WAITS = [3, 5, 8, 12, 20]
MODES = ['strict', 'soft_mid', 'touch_bull', 'support_hold']


def fnum(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '':
            return d
        v = float(x)
        return v if not math.isnan(v) else d
    except Exception:
        return d


def ds(b: dict[str, Any]) -> str:
    return str(b.get('t', b.get('date', ''))).replace('.0', '')[:8]


def symbol_from_path(p: Path) -> str:
    stem = p.stem.replace('_daily_750', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def mode_ok(mode: str, b: dict[str, Any], zl: float, zh: float) -> bool:
    o = fnum(b.get('o')); c = fnum(b.get('c')); h = fnum(b.get('h')); l = fnum(b.get('l'))
    if any(math.isnan(x) for x in [o, c, h, l]) or h <= l:
        return False
    # Must at least touch the demand body/zone vicinity; otherwise it is chase, not retest.
    if l > zh * 1.005:
        return False
    rng = h - l
    if mode == 'strict':
        return c >= zh and c > o and (c - l) / rng >= 0.55
    if mode == 'soft_mid':
        return c >= (zl + zh) / 2 and (c - l) / rng >= 0.45
    if mode == 'touch_bull':
        return c > o and c >= zl
    if mode == 'support_hold':
        return c >= zl
    return False


def replay_exit(bars: list[dict[str, Any]], entry_i: int, entry: float, sl: float, rr: float = 1.5, max_hold: int = 10) -> dict[str, Any] | None:
    # A-share T+1: first exit after entry day.
    if entry_i + 1 >= len(bars):
        return None
    tp = entry + (entry - sl) * rr
    last = min(len(bars) - 1, entry_i + max_hold)
    exit_i = last
    exit_p = fnum(bars[last].get('c'))
    reason = f'TIME{max_hold}'
    for i in range(entry_i + 1, last + 1):
        lo = fnum(bars[i].get('l')); hi = fnum(bars[i].get('h'))
        if lo <= sl:
            exit_i = i; exit_p = sl; reason = 'SL'; break
        if hi >= tp:
            exit_i = i; exit_p = tp; reason = 'TP'; break
    return {
        'exit_date': ds(bars[exit_i]),
        'exit_idx': exit_i,
        'exit_reason': reason,
        'pnl_pct': (exit_p / entry - 1) * 100,
        't1_violation': ds(bars[exit_i]) == ds(bars[entry_i]),
    }


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    if len(df) == 0:
        return {'n': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce')
    years = df['entry_date'].astype(str).str[:4]
    yc = years.value_counts().sort_index().to_dict()
    ywr = {str(y): round(float((pnl[years == y] > 0).mean() * 100), 2) for y in sorted(years.dropna().unique())}
    return {
        'n': int(len(df)),
        'wr': round(float((pnl > 0).mean() * 100), 4),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': int((pnl <= 0).sum()),
        'micro': round(float(((pnl > 0) & (pnl < 1)).mean() * 100), 4),
        'min_year_n': int(min(yc.values()) if yc else 0),
        'year_counts': {str(k): int(v) for k, v in yc.items()},
        'year_wr': ywr,
        'all_year_wr_min': round(float(min(ywr.values()) if ywr else 0), 2),
        'symbols': int(df['symbol'].nunique()),
        'per_stock_3y': round(float(len(df) / max(df['symbol'].nunique(), 1)), 4),
        't1': int(df.get('t1_violation', pd.Series(False, index=df.index)).fillna(False).astype(bool).sum()),
    }


def scan_symbol(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    symbol = symbol_from_path(path)
    try:
        bars = json.loads(path.read_text())
    except Exception:
        return {'symbol': symbol, 'load_ok': False}, []
    if len(bars) < 90:
        return {'symbol': symbol, 'load_ok': False, 'bars': len(bars)}, []

    # Primitive arrays.
    ssl_idx: list[int] = []
    bullish_idx: list[int] = []
    bearish_idx: list[int] = []
    bos_by_lb: dict[int, list[int]] = {lb: [] for lb in BOS_LOOKBACKS}
    for i in range(40, len(bars) - 2):
        d = ds(bars[i])
        if d[:4] not in YEARS:
            continue
        o = fnum(bars[i].get('o')); c = fnum(bars[i].get('c')); h = fnum(bars[i].get('h')); l = fnum(bars[i].get('l'))
        if any(math.isnan(x) for x in [o, c, h, l]) or h <= l:
            continue
        if c > o:
            bullish_idx.append(i)
        if c < o:
            bearish_idx.append(i)
        prev20 = bars[i - 20:i]
        pl = min(fnum(x.get('l')) for x in prev20)
        if l < pl and c > pl:
            ssl_idx.append(i)
        for lb in BOS_LOOKBACKS:
            ph = max(fnum(x.get('h')) for x in bars[i - lb:i])
            if c > o and c > ph:
                bos_by_lb[lb].append(i)

    ssl_set = set(ssl_idx)
    stat: dict[str, Any] = {
        'symbol': symbol, 'load_ok': True, 'bars': len(bars),
        'ssl_n': len(ssl_idx), 'bullish_n': len(bullish_idx), 'bearish_n': len(bearish_idx),
        **{f'bos{lb}_n': len(v) for lb, v in bos_by_lb.items()},
    }

    rows: list[dict[str, Any]] = []
    # One row per unique executable entry per parameter spec; later summary dedupes where needed.
    for lb, bos_events in bos_by_lb.items():
        for event_i in bos_events:
            event_date = ds(bars[event_i])
            if event_date[:4] not in YEARS:
                continue
            last_ssl_by_win = {}
            for win in SSL_WINDOWS:
                if win == 0:
                    last_ssl_by_win[win] = None
                else:
                    last = None
                    for j in range(max(40, event_i - win), event_i):
                        if j in ssl_set:
                            last = j
                    last_ssl_by_win[win] = last
            for dlb in DEMAND_LOOKBACKS:
                demand_i = None
                for k in range(event_i - 1, max(event_i - dlb - 1, -1), -1):
                    if fnum(bars[k].get('c')) < fnum(bars[k].get('o')):
                        demand_i = k
                        break
                if demand_i is None:
                    continue
                zl = fnum(bars[demand_i].get('l'))
                zh = max(fnum(bars[demand_i].get('o')), fnum(bars[demand_i].get('c')))
                if math.isnan(zl) or math.isnan(zh) or zl <= 0 or zh <= zl:
                    continue
                zone_age = event_i - demand_i
                first_by_mode: dict[str, int] = {}
                for mode in MODES:
                    for ri in range(event_i + 1, min(event_i + max(WAITS), len(bars) - 2) + 1):
                        if mode_ok(mode, bars[ri], zl, zh):
                            first_by_mode[mode] = ri
                            break
                for ssl_win, ssl_i in last_ssl_by_win.items():
                    if ssl_win > 0 and ssl_i is None:
                        continue
                    ssl_relation = 'NO_REQUIREMENT' if ssl_win == 0 else ('SSL_BEFORE_DEMAND' if ssl_i < demand_i else ('SSL_ON_DEMAND' if ssl_i == demand_i else 'SSL_AFTER_DEMAND_BEFORE_BOS'))
                    ssl_age = None if ssl_i is None else event_i - ssl_i
                    for mode, ri in first_by_mode.items():
                        delay = ri - event_i
                        for wait in WAITS:
                            if delay > wait:
                                continue
                            entry_i = ri + 1
                            if entry_i >= len(bars):
                                continue
                            entry = fnum(bars[entry_i].get('o'))
                            sl = zl * 0.99
                            risk = (entry / sl - 1) * 100
                            chase = (entry / zh - 1) * 100
                            if not (0.8 <= risk <= 12.0):
                                continue
                            ex = replay_exit(bars, entry_i, entry, sl)
                            if ex is None:
                                continue
                            rows.append({
                                'symbol': symbol, 'entry_date': ds(bars[entry_i]), 'entry_idx': entry_i,
                                'event_date': event_date, 'event_idx': event_i, 'zone_date': ds(bars[demand_i]), 'zone_idx': demand_i,
                                'bos_lb': lb, 'demand_lb': dlb, 'ssl_win': ssl_win, 'wait': wait, 'mode': mode,
                                'ssl_relation': ssl_relation, 'ssl_age': ssl_age, 'zone_age': zone_age, 'retest_delay': delay,
                                'risk_pct': risk, 'chase_pct': chase,
                                **ex,
                            })
    return stat, rows


def describe_series(s: pd.Series) -> dict[str, Any]:
    if len(s) == 0:
        return {}
    return {k: round(float(v), 4) for k, v in s.describe(percentiles=[.25, .5, .75, .9, .95]).to_dict().items()}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = sorted(KDIR.glob('*_daily_750.json'))
    stats = []
    rows = []
    for i, p in enumerate(paths, 1):
        st, rs = scan_symbol(p)
        stats.append(st); rows.extend(rs)
        if i % 500 == 0:
            print(f'scanned {i}/{len(paths)} variant_rows={len(rows)}', flush=True)

    stats_df = pd.DataFrame(stats)
    rows_df = pd.DataFrame(rows)
    stats_df.to_csv(OUT / 'v276_per_stock_primitive_counts.csv', index=False)
    if rows_df.empty:
        raise SystemExit('no sequence rows')
    rows_df = rows_df[rows_df['entry_date'].astype(str).str[:4].isin(YEARS)].copy()
    rows_df['key_spec'] = rows_df[['symbol','entry_date','bos_lb','demand_lb','ssl_win','wait','mode']].astype(str).agg('|'.join, axis=1)
    rows_df = rows_df.drop_duplicates('key_spec')
    rows_df.to_csv(OUT / 'v276_variant_sequence_rows.csv.gz', index=False, compression='gzip')

    # Supply-chain attrition: unique BOS events through sequential gates, not outcome filtering.
    supply_rows = []
    for lb in BOS_LOOKBACKS:
        bos_total = int(stats_df.get(f'bos{lb}_n', pd.Series(dtype=float)).fillna(0).sum())
        for dlb in DEMAND_LOOKBACKS:
            for ssl_win in SSL_WINDOWS:
                subset = rows_df[(rows_df.bos_lb == lb) & (rows_df.demand_lb == dlb) & (rows_df.ssl_win == ssl_win)]
                # event-level counts after each gate are inferred from generated rows; retest-mode split below gives executable density.
                event_with_entry = int(subset[['symbol','event_idx']].drop_duplicates().shape[0]) if len(subset) else 0
                for mode in MODES:
                    for wait in WAITS:
                        g = subset[(subset['mode'] == mode) & (subset['wait'] == wait)]
                        if len(g) == 0:
                            continue
                        # Dedup actual executable entries for density and outcome.
                        gd = g.drop_duplicates(['symbol','entry_date'], keep='first').copy()
                        m = metrics(gd)
                        if m['n'] < 100:
                            continue
                        supply_rows.append({
                            'bos_lb': lb, 'demand_lb': dlb, 'ssl_win': ssl_win, 'mode': mode, 'wait': wait,
                            'bos_events_total': bos_total, 'events_with_any_entry_same_prefix': event_with_entry,
                            'event_to_entry_pct_of_bos': round(event_with_entry / max(bos_total, 1) * 100, 4),
                            **m,
                        })
    supply_df = pd.DataFrame(supply_rows).sort_values(['wr','avg','n'], ascending=[False,False,False])
    supply_df.to_csv(OUT / 'v276_parameter_supply_quality_surface.csv', index=False)

    # Timeline relation surface: is SSL-before-demand actually useful, or is it a volume killer?
    timeline_rows = []
    for cols in [
        ['ssl_relation'], ['ssl_win'], ['zone_age'], ['retest_delay'], ['mode'],
        ['ssl_relation','mode'], ['ssl_relation','retest_delay'], ['ssl_win','mode','wait'],
        ['bos_lb','demand_lb','ssl_win','mode','wait'],
    ]:
        for key, g in rows_df.groupby(cols, dropna=False):
            if len(g) < 300:
                continue
            gd = g.drop_duplicates(['symbol','entry_date'], keep='first')
            if len(gd) < 100:
                continue
            timeline_rows.append({'surface': '+'.join(cols), 'key': '|'.join(map(str, key if isinstance(key, tuple) else (key,))), **metrics(gd)})
    timeline_df = pd.DataFrame(timeline_rows).sort_values(['wr','avg','n'], ascending=[False,False,False])
    timeline_df.to_csv(OUT / 'v276_timeline_relation_surfaces.csv', index=False)

    # Primitive density and attrition facts.
    ok_stats = stats_df[stats_df.get('load_ok', False) == True].copy()
    primitive_summary = {
        'stocks': int(len(ok_stats)),
        'ssl_total': int(ok_stats['ssl_n'].sum()),
        'ssl_per_stock': describe_series(ok_stats['ssl_n']),
        'bos10_total': int(ok_stats['bos10_n'].sum()),
        'bos10_per_stock': describe_series(ok_stats['bos10_n']),
        'bos20_total': int(ok_stats['bos20_n'].sum()),
        'bos20_per_stock': describe_series(ok_stats['bos20_n']),
        'bos40_total': int(ok_stats['bos40_n'].sum()),
        'bos40_per_stock': describe_series(ok_stats['bos40_n']),
    }
    unique_entries = rows_df.drop_duplicates(['symbol','entry_date'], keep='first')
    best_quality = supply_df.head(30).to_dict(orient='records') if len(supply_df) else []
    best_volume = supply_df.sort_values(['n','wr','avg'], ascending=[False,False,False]).head(30).to_dict(orient='records') if len(supply_df) else []
    best_timeline = timeline_df.head(30).to_dict(orient='records') if len(timeline_df) else []

    summary = {
        'version': 'V276_SEQUENCE_SUPPLY_CHAIN_ATTRITION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'out_dir': str(OUT),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'kline_dir': str(KDIR), 'kline_files': len(paths), 'years': sorted(YEARS)},
        'primitive_summary': primitive_summary,
        'variant_rows': int(len(rows_df)),
        'unique_entry_rows_any_spec': metrics(unique_entries),
        'best_parameter_supply_quality': best_quality,
        'largest_parameter_surfaces': best_volume,
        'best_timeline_relation_surfaces': best_timeline,
        'artifacts': {
            'per_stock_primitive_counts': str(OUT / 'v276_per_stock_primitive_counts.csv'),
            'variant_sequence_rows': str(OUT / 'v276_variant_sequence_rows.csv.gz'),
            'parameter_supply_quality_surface': str(OUT / 'v276_parameter_supply_quality_surface.csv'),
            'timeline_relation_surfaces': str(OUT / 'v276_timeline_relation_surfaces.csv'),
        },
        'decision': 'NO_PRODUCTION_WRITE__SEQUENCE_ATTRITION_DIAGNOSIS_ONLY',
    }
    (OUT / 'v276_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:14000])


if __name__ == '__main__':
    main()
