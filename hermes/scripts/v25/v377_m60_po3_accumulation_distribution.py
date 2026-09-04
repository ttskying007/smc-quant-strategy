#!/usr/bin/env python3
"""V377 no-write: causal 60m PO3 accumulation→manipulation→distribution replay.

This is a different semantic family from V376: an observable eight-bar narrow
accumulation must be swept below its own lower boundary, price must distribute
above its own upper boundary, then revisit and reclaim the event-anchored OB.
No pivots, bars, or results after entry may define the setup. One symbol has one
serial A-share position at a time; exits begin only on T+1.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
CACHE = ROOT / 'intraday_cache' / 'sina_m60_v1'
AUDIT = ROOT / 'smc_audit'
V373 = AUDIT / 'v373_sina_m60_strict_coverage_latest.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v377_m60_po3_accumulation_distribution_no_write_{TS}'
LATEST = AUDIT / 'v377_m60_po3_accumulation_distribution_latest.json'
SLOTS = {'10:30:00', '11:30:00', '14:00:00', '15:00:00'}


def f(x: object) -> float:
    return float(x)


def day(t: str) -> str:
    return t[:10].replace('-', '')


def load(path: Path) -> list[dict]:
    with gzip.open(path, 'rt') as h:
        raw = json.load(h)
    bars = []
    for x in raw:
        t = str(x.get('day') or '')
        if len(t) < 19:
            continue
        d = day(t)
        if not ('20230101' <= d <= '20260710'):
            continue
        try:
            bars.append({'t': t, 'd': d, 'o': f(x['open']), 'h': f(x['high']),
                         'l': f(x['low']), 'c': f(x['close']), 'v': f(x.get('volume', 0))})
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda x: x['t'])
    per = defaultdict(list)
    for i, b in enumerate(bars):
        per[b['d']].append(i)
    valid = {d for d, ids in per.items() if len(ids) == 4 and {bars[i]['t'][-8:] for i in ids} == SLOTS}
    return [b for b in bars if b['d'] in valid]


def pivots(bars: list[dict]) -> tuple[dict[int, tuple[int, float]], dict[int, tuple[int, float]]]:
    """3-left/3-right pivots scheduled at their first observable bar."""
    high_visible, low_visible = {}, {}
    for p in range(3, len(bars) - 3):
        hi, lo = bars[p]['h'], bars[p]['l']
        window = bars[p - 3:p + 4]
        if hi == max(x['h'] for x in window) and sum(x['h'] == hi for x in window) == 1:
            high_visible[p + 3] = (p, hi)
        if lo == min(x['l'] for x in window) and sum(x['l'] == lo for x in window) == 1:
            low_visible[p + 3] = (p, lo)
    return high_visible, low_visible


def nearest_bear_ob(bars: list[dict], start: int, event: int) -> tuple[int, float, float] | None:
    for i in range(event - 1, max(start - 10, event - 11), -1):
        if bars[i]['c'] < bars[i]['o']:
            return i, bars[i]['l'], bars[i]['h']
    return None


def replay(bars: list[dict], entry_i: int, sl: float, tp: float) -> dict | None:
    entry = bars[entry_i]['o']; eday = bars[entry_i]['d']
    if not (entry > sl > 0 and tp > entry):
        return None
    # T+1: inspect exits only from a later trading date. Same-bar collision is SL first.
    for k in range(entry_i + 1, min(len(bars), entry_i + 41)):
        b = bars[k]
        if b['d'] == eday:
            continue
        if b['l'] <= sl:
            return {'exit_i': k, 'exit_time': b['t'], 'exit_date': b['d'], 'exit_price': sl, 'reason': 'SL_HIT'}
        if b['h'] >= tp:
            return {'exit_i': k, 'exit_time': b['t'], 'exit_date': b['d'], 'exit_price': tp, 'reason': 'TP_HIT'}
    eligible = [k for k in range(entry_i + 1, min(len(bars), entry_i + 41)) if bars[k]['d'] != eday]
    if not eligible:
        return None
    k = eligible[-1]
    return {'exit_i': k, 'exit_time': bars[k]['t'], 'exit_date': bars[k]['d'], 'exit_price': bars[k]['c'], 'reason': 'TIME_10_SESSIONS'}


def one_symbol(symbol: str, path: Path) -> list[dict]:
    bars = load(path)
    if len(bars) < 100:
        return []
    high_visible, low_visible = pivots(bars)
    known_hi: list[tuple[int, float]] = []
    known_lo: list[tuple[int, float]] = []
    active = []
    out = []
    cooldown = -99
    for i, b in enumerate(bars):
        if i in high_visible:
            known_hi.append(high_visible[i])
        if i in low_visible:
            known_lo.append(low_visible[i])
        known_hi = [(p, price) for p, price in known_hi if i - p <= 60]
        known_lo = [(p, price) for p, price in known_lo if i - p <= 60]
        # Advance existing causal state machines before possibly starting another.
        next_active = []
        for s in active:
            age = i - s['sweep_i']
            if age > 30:
                continue
            if s['state'] == 'WAIT_MSS':
                if i > s['sweep_i'] and b['c'] > s['break_level'] * 1.002:
                    ob = nearest_bear_ob(bars, s['sweep_i'], i)
                    if ob:
                        s.update(state='WAIT_TOUCH', mss_i=i, ob_i=ob[0], zl=ob[1], zh=ob[2])
                    else:
                        continue
            elif s['state'] == 'WAIT_TOUCH':
                if b['c'] < s['zl']:
                    continue
                if i > s['mss_i'] and b['l'] <= s['zh']:
                    s.update(state='WAIT_RECLAIM', touch_i=i)
            elif s['state'] == 'WAIT_RECLAIM':
                if b['c'] < s['zl']:
                    continue
                if i > s['touch_i'] and b['c'] > s['zh']:
                    s.update(state='WAIT_HOLD', reclaim_i=i)
            elif s['state'] == 'WAIT_HOLD':
                if b['c'] < s['zl']:
                    continue
                if i > s['reclaim_i'] and b['c'] > s['zh'] and b['l'] >= s['zl']:
                    s['hold_i'] = i
                    entry_i = i + 1
                    if entry_i < len(bars):
                        entry = bars[entry_i]['o']; sl = s['zl'] * 0.997
                        risk = (entry - sl) / entry * 100 if entry else 0
                        targets = [price for p, price in known_hi if p + 3 <= i and price > entry]
                        target = min(targets) if targets else 0.0
                        rr = (target - entry) / (entry - sl) if entry > sl and target else 0.0
                        if 1.5 <= risk <= 10 and 1.5 <= rr <= 5:
                            result = replay(bars, entry_i, sl, target)
                            if result:
                                pnl = (result['exit_price'] / entry - 1) * 100
                                out.append({'symbol': symbol, 'sweep_time': bars[s['sweep_i']]['t'],
                                            'acc_start_time': bars[s['acc_start_i']]['t'],
                                            'acc_end_time': bars[s['acc_end_i']]['t'],
                                            'mss_time': bars[s['mss_i']]['t'],
                                            'ob_time': bars[s['ob_i']]['t'], 'touch_time': bars[s['touch_i']]['t'],
                                            'reclaim_time': bars[s['reclaim_i']]['t'], 'hold_time': b['t'],
                                            'entry_time': bars[entry_i]['t'], 'entry_date': bars[entry_i]['d'],
                                            'entry_price': entry, 'zone_low': s['zl'], 'zone_high': s['zh'], 'sl': sl,
                                            'tp': target, 'risk_pct': risk, 'rr': rr, 'exit_date': result['exit_date'],
                                            'exit_time': result['exit_time'], 'exit_price': result['exit_price'], 'exit_reason': result['reason'],
                                            'pnl_pct': pnl, 'hold_bars': result['exit_i'] - entry_i,
                                            't1_violation': result['exit_date'] == bars[entry_i]['d']})
                                cooldown = i + 8
                    continue
            next_active.append(s)
        active = next_active
        if i < 30 or i < cooldown or not known_hi:
            continue
        # PO3: eight fully closed bars form an observable accumulation.  The
        # current bar manipulates below its own range low and reclaims it; later
        # WAIT_MSS requires distribution through that same range high.
        acc = bars[i - 8:i]
        acc_low, acc_high = min(x['l'] for x in acc), max(x['h'] for x in acc)
        if not (acc_low > 0 and (acc_high / acc_low - 1) <= .03):
            continue
        if b['l'] < acc_low * .997 and b['c'] > acc_low:
            active.append({'state': 'WAIT_MSS', 'sweep_i': i, 'pool_i': i - 1, 'pool': acc_low,
                           'acc_start_i': i - 8, 'acc_end_i': i - 1, 'break_level': acc_high})
    # Same-open variants are not multiple independent orders. Choose the newest
    # causal sweep context before looking at outcomes, then replay one position
    # at a time for this symbol.
    newest_by_entry = {}
    for row in out:
        prior = newest_by_entry.get(row['entry_time'])
        if prior is None or row['sweep_time'] > prior['sweep_time']:
            newest_by_entry[row['entry_time']] = row
    executed = []
    position_until = ''
    for row in sorted(newest_by_entry.values(), key=lambda x: x['entry_time']):
        if position_until and row['entry_time'] <= position_until:
            continue
        executed.append(row)
        position_until = row['exit_time']
    return executed


def metrics(rows: list[dict]) -> dict:
    if not rows:
        return {'n': 0}
    wins = [r['pnl_pct'] > 0 for r in rows]
    years = defaultdict(list)
    for r in rows: years[r['entry_date'][:4]].append(r)
    yc = {y: len(v) for y, v in sorted(years.items())}
    ywr = {y: round(sum(x['pnl_pct'] > 0 for x in v) / len(v) * 100, 2) for y, v in sorted(years.items())}
    return {'n': len(rows), 'symbols': len({r['symbol'] for r in rows}), 'wr': round(sum(wins) / len(rows) * 100, 4),
            'avg_pnl': round(sum(r['pnl_pct'] for r in rows) / len(rows), 4),
            'micro_pct': round(sum(0 < r['pnl_pct'] < 1 for r in rows) / len(rows) * 100, 4),
            'sl_pct': round(sum(r['exit_reason'] == 'SL_HIT' for r in rows) / len(rows) * 100, 4),
            't1_violations': sum(bool(r['t1_violation']) for r in rows), 'year_counts': yc, 'year_wr': ywr,
            'min_year_n': min(yc.values()), 'min_year_wr': min(ywr.values())}


def main() -> None:
    source = json.loads(V373.read_text())
    if source['counts']['missing_day_count']:
        raise RuntimeError('V373 has missing calendar days; generator prohibited')
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    files = sorted(CACHE.glob('*_m60_sina.json.gz'))
    for n, path in enumerate(files, 1):
        code, exchange, *_ = path.name.split('_')
        rows.extend(one_symbol(f'{code}.{exchange}', path))
        if n % 500 == 0:
            print(json.dumps({'processed': n, 'total': len(files), 'events': len(rows)}), flush=True)
    fields = list(rows[0]) if rows else ['symbol']
    with (OUT / 'v377_trades.csv').open('w', newline='') as h:
        writer = csv.DictWriter(h, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    m = metrics(rows)
    gate = (m.get('n', 0) >= 300 and m.get('min_year_n', 0) >= 40 and m.get('wr', 0) >= 87 and
            m.get('avg_pnl', 0) >= 6.8 and m.get('min_year_wr', 0) >= 84 and m.get('micro_pct', 100) <= 1 and m.get('t1_violations', 1) == 0)
    report = {'version': 'V377_FULL_HISTORY_CAUSAL_60M_PO3_ACCUMULATION_DISTRIBUTION_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': '8 completed 60m bars with <=3% range -> current bar sweeps below and reclaims accumulation low -> close distributes >0.2% above accumulation high -> event-anchored bearish OB -> first touch -> reclaim -> hold -> next 60m open; one newest-sweep candidate per symbol/open and no overlapping positions; raw 60m only; T+1 exits',
              'source': {'v373_decision': source['decision'], 'hard_invalid_source_days': source['counts']['bad_slot_day_count'], 'all_invalid_days_are_excluded_by_per-day-bar-boundary': True},
              'metrics': m, 'production_gate': {'n>=300': m.get('n',0)>=300, 'min_year_n>=40':m.get('min_year_n',0)>=40, 'wr>=87':m.get('wr',0)>=87, 'avg>=6.8':m.get('avg_pnl',0)>=6.8, 'year_wr>=84':m.get('min_year_wr',0)>=84, 'micro<=1':m.get('micro_pct',100)<=1, 't1==0':m.get('t1_violations',1)==0},
              'decision': 'RESEARCH_CANDIDATE_ONLY__INDEPENDENT_SEMANTIC_ORACLE_REQUIRED' if gate else 'NO_PRODUCTION_PASS__CAUSAL_GENERATOR_CLOSED_OR_REVISE_SEMANTICS',
              'artifacts': {'trades': str(OUT / 'v377_trades.csv'), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2); (OUT / 'v377_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
