#!/usr/bin/env python3
"""V287 no-write: 60min-first same-source SMC generator.

V284 proved daily zones cannot be rescued by looking backward into 60m sequences.
This script flips the direction: create the POI from 60m sweep/reclaim/MSS first,
then map it to next daily T+1 execution. It is intentionally small and auditable.
No production/frontend/watchlist writes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
K60_DIRS = [BASE / 'kline_cache_60min', BASE / 'kline_cache']
KDAY = BASE / 'kline_cache'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v287_60min_first_smc_generator_no_write_{TS}'
LATEST = AUDIT / 'v287_60min_first_smc_generator_latest.json'
YEARS = {'2025', '2026'}  # 60m cache is recent only.


def sf(x: Any, d: float = math.nan) -> float:
    try:
        if x is None or x == '': return d
        v = float(x); return v if not math.isnan(v) else d
    except Exception:
        return d


def dn(x: Any) -> str:
    s = ''.join(ch for ch in str(x or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def sym_from_60(p: Path) -> str:
    stem = p.stem.replace('_60min_500', '').replace('_60min_200', '')
    code, exch = stem.split('_', 1)
    return f'{code}.{exch}'


def daily_path(sym: str) -> Path:
    code, exch = sym.split('.')
    return KDAY / f'{code}_{exch}_daily_750.json'


def blank() -> dict[str, Any]:
    return {'n': 0, 'wins': 0, 'sum': 0.0, 'loss': 0, 'micro': 0,
            'tp': 0, 'sl': 0, 'time': 0, 'years': defaultdict(lambda: [0, 0]), 'symbols': set()}


def add(a: dict[str, Any], r: dict[str, Any]) -> None:
    pnl = sf(r.get('pnl'), 0.0); y = str(r.get('year') or '') ; reason = str(r.get('reason') or '')
    a['n'] += 1; a['wins'] += pnl > 0; a['sum'] += pnl; a['loss'] += pnl <= 0; a['micro'] += 0 < pnl < 1
    a['tp'] += reason == 'TP'; a['sl'] += reason == 'SL'; a['time'] += reason.startswith('TIME')
    a['years'][y][0] += 1; a['years'][y][1] += pnl > 0; a['symbols'].add(r.get('symbol', ''))


def metrics(a: dict[str, Any], stock_count: int = 4655) -> dict[str, Any]:
    n = int(a['n'])
    if not n: return {'n': 0}
    yc = {y: int(v[0]) for y, v in sorted(a['years'].items()) if v[0]}
    ywr = {y: round(v[1] / v[0] * 100, 2) for y, v in sorted(a['years'].items()) if v[0]}
    return {'n': n, 'wr': round(a['wins'] / n * 100, 4), 'avg': round(a['sum'] / n, 4),
            'loss': int(a['loss']), 'micro': round(a['micro'] / n * 100, 2),
            'tp_pct': round(a['tp'] / n * 100, 2), 'sl_pct': round(a['sl'] / n * 100, 2),
            'time_pct': round(a['time'] / n * 100, 2), 'symbols': len(a['symbols']),
            'per_stock_2y_all_stocks': round(n / stock_count, 4), 'yc': yc, 'ywr': ywr,
            'min_year_n': min(yc.values()) if yc else 0, 'minwr': round(min(ywr.values()) if ywr else 0, 2)}


def load_json(p: Path) -> list[dict[str, Any]]:
    try:
        arr = json.loads(p.read_text())
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


def replay_daily(daily: list[dict[str, Any]], signal_date: str, entry_price_hint: float, sl: float, rr: float = 1.5, max_hold: int = 10):
    bars = [(dn(b.get('t') or b.get('date')), sf(b.get('o')), sf(b.get('h')), sf(b.get('l')), sf(b.get('c'))) for b in daily]
    bars = [b for b in bars if b[0] and not any(math.isnan(x) for x in b[1:])]
    bars.sort(key=lambda x: x[0])
    idx = next((i for i, b in enumerate(bars) if b[0] > signal_date), None)
    if idx is None or idx + 1 >= len(bars): return None
    entry_date, entry, *_ = bars[idx]
    if entry <= 0 or sl <= 0 or sl >= entry: return None
    risk_pct = (entry - sl) / entry * 100
    if risk_pct < 1 or risk_pct > 12: return None
    tp = entry + (entry - sl) * rr
    exit_date = ''; exit_price = bars[min(len(bars) - 1, idx + max_hold)][4]; reason = f'TIME{max_hold}'
    # Strict T+1: exits start from day after entry.
    for k in range(idx + 1, min(len(bars), idx + max_hold + 1)):
        d, o, h, l, c = bars[k]
        if l <= sl:
            exit_date, exit_price, reason = d, sl, 'SL'; break
        if h >= tp:
            exit_date, exit_price, reason = d, tp, 'TP'; break
    if not exit_date:
        exit_date = bars[min(len(bars) - 1, idx + max_hold)][0]
    pnl = (exit_price / entry - 1) * 100
    return {'entry_date': entry_date, 'entry': entry, 'exit_date': exit_date, 'exit_price': exit_price,
            'pnl': pnl, 'reason': reason, 'risk_pct': risk_pct, 'tp': tp, 't1': exit_date == entry_date}


def day_regime(daily: list[dict[str, Any]], date: str) -> str:
    seq = [(dn(b.get('t') or b.get('date')), sf(b.get('c')), sf(b.get('h')), sf(b.get('l'))) for b in daily]
    seq = [x for x in seq if x[0] and not any(math.isnan(v) for v in x[1:])]
    seq.sort(key=lambda x: x[0])
    i = next((j for j, x in enumerate(seq) if x[0] >= date), len(seq)) - 1
    if i < 60: return 'REGIME_NA'
    c = seq[i][1]
    hi20 = max(x[2] for x in seq[i-20:i]); lo20 = min(x[3] for x in seq[i-20:i])
    hi60 = max(x[2] for x in seq[i-60:i]); lo60 = min(x[3] for x in seq[i-60:i])
    pos60 = (c - lo60) / (hi60 - lo60) * 100 if hi60 > lo60 else 50
    if c > hi20: return 'DAILY_BREAKOUT'
    if c < lo20: return 'DAILY_BREAKDOWN'
    if pos60 < 35: return 'DAILY_LOW'
    if pos60 > 65: return 'DAILY_HIGH'
    return 'DAILY_RANGE'


def generate_for_symbol(sym: str, bars60: list[dict[str, Any]], daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    b60 = []
    for b in bars60:
        t = str(b.get('t') or b.get('date') or '')
        d = dn(t); o = sf(b.get('o')); h = sf(b.get('h')); l = sf(b.get('l')); c = sf(b.get('c')); v = sf(b.get('v'), 0.0)
        if len(t) >= 12 and d and not any(math.isnan(x) for x in [o, h, l, c]): b60.append({'t': t, 'd': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
    b60.sort(key=lambda x: x['t'])
    out = []
    last_signal_i = -99
    for i in range(30, len(b60) - 5):
        if i - last_signal_i < 8: continue
        d = b60[i]['d']
        if d[:4] not in YEARS: continue
        prev20 = b60[i-20:i]
        prev_low = min(x['l'] for x in prev20); prev_high8 = max(x['h'] for x in b60[i-8:i])
        sweep_depth = (prev_low / b60[i]['l'] - 1) * 100 if b60[i]['l'] > 0 else 0
        if not (sweep_depth >= 0.25 and b60[i]['c'] > prev_low): continue
        mss_j = None
        for j in range(i, min(len(b60), i + 5)):
            local_high = max(x['h'] for x in b60[max(0, j-8):j]) if j > 0 else prev_high8
            if b60[j]['c'] > local_high * 1.001:
                mss_j = j; break
        if mss_j is None: continue
        zone_low = b60[i]['l']; zone_high = prev_low
        # Same-source POI: 60m sweep wick -> reclaimed level. Stop under wick with small buffer.
        sl = zone_low - max((zone_high - zone_low) * 0.5, zone_low * 0.003)
        replay = replay_daily(daily, b60[mss_j]['d'], b60[mss_j]['c'], sl)
        if not replay: continue
        entry_gap = (replay['entry'] / b60[mss_j]['c'] - 1) * 100
        if entry_gap > 8: continue
        family = '60M_SWEEP_RECLAIM_MSS'
        if mss_j == i: family = '60M_SAMEBAR_TAKEOVER'
        elif mss_j - i <= 2: family = '60M_FAST_TAKEOVER'
        else: family = '60M_SLOW_TAKEOVER'
        out.append({'symbol': sym, 'signal_date': b60[mss_j]['d'], 'signal_time': b60[mss_j]['t'], 'year': replay['entry_date'][:4],
                    'family': family, 'daily_regime': day_regime(daily, b60[mss_j]['d']), 'sweep_depth': sweep_depth,
                    'mss_delay': mss_j - i, 'zone_low': zone_low, 'zone_high': zone_high, 'sl': sl,
                    'entry_gap_pct': entry_gap, **replay})
        last_signal_i = i
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for d in K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            try: sym = sym_from_60(p)
            except Exception: continue
            if sym not in files or p.stat().st_size > files[sym].stat().st_size:
                files[sym] = p
    rows = []
    for sym, fp in sorted(files.items()):
        daily = load_json(daily_path(sym)); bars60 = load_json(fp)
        if len(daily) < 80 or len(bars60) < 100: continue
        rows.extend(generate_for_symbol(sym, bars60, daily))

    all_agg = blank(); by_family = defaultdict(blank); by_regime = defaultdict(blank); by_combo = defaultdict(blank)
    t1 = 0
    for r in rows:
        add(all_agg, r); add(by_family[r['family']], r); add(by_regime[r['daily_regime']], r); add(by_combo[(r['family'], r['daily_regime'])], r)
        t1 += bool(r.get('t1'))
    fam = [{'family': k, **metrics(v)} for k, v in by_family.items()]
    reg = [{'daily_regime': k, **metrics(v)} for k, v in by_regime.items()]
    combo = [{'family': k[0], 'daily_regime': k[1], **metrics(v)} for k, v in by_combo.items()]
    for arr in [fam, reg, combo]: arr.sort(key=lambda x: (x.get('minwr', 0), x.get('wr', 0), x.get('avg', 0), x.get('n', 0)), reverse=True)

    csv_path = OUT / 'v287_60min_first_events.csv'
    fields = ['symbol','signal_date','signal_time','year','family','daily_regime','sweep_depth','mss_delay','zone_low','zone_high','sl','entry_gap_pct','entry_date','entry','exit_date','exit_price','pnl','reason','risk_pct','tp','t1']
    with csv_path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k: r.get(k) for k in fields})
    summary = {'version': 'V287_60MIN_FIRST_SAME_SOURCE_GENERATOR_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
               'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
               'inputs': {'sixty_min_symbols': len(files), 'years': sorted(YEARS), 'note': '60m cache is recent; not full 2023-2024 coverage'},
               'all_events': metrics(all_agg), 't1_violations': t1, 'family_breakdown': fam, 'daily_regime_breakdown': reg,
               'family_regime_breakdown': combo[:30], 'artifacts': {'events': str(csv_path)},
               'decision': 'Tests same-source 60m POI generation before daily execution; coverage limited by 60m cache.'}
    (OUT / 'v287_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'out': str(OUT), 'latest': str(LATEST), 'all': summary['all_events'], 't1': t1,
                      'top_family': fam[:5], 'top_combo': combo[:8]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
