#!/usr/bin/env python3
"""V376 no-write: causal 60m nearest-swing MSS with serial A-share execution.

This keeps V375's causal signal definition and repairs its execution contract:
for one symbol, concurrent or same-open candidates cannot create multiple buys.
At the same entry open, retain only the most recent sweep context (known before
entry); then execute chronologically and block later entries until the existing
position's realized exit. This is an execution replay rule, not a PnL filter.
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
OUT = AUDIT / f'v376_m60_nearest_swing_mss_serial_execution_no_write_{TS}'
LATEST = AUDIT / 'v376_m60_nearest_swing_mss_serial_execution_latest.json'
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
                                            'break_pivot_time': bars[s['break_pivot_i']]['t'],
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
        if i < 30 or i < cooldown or not known_lo or not known_hi:
            continue
        # SSL sweep of a confirmed pivot visible before this bar.  MSS must break
        # the nearest prior confirmed swing high; using the maximum high would
        # turn a local reversal test into a delayed long-window breakout.
        pools = [(p, price) for p, price in known_lo if 3 <= i - p <= 60 and b['l'] < price * .997 and b['c'] > price]
        highs = [(p, price) for p, price in known_hi if p < i and i - p <= 60]
        if pools and highs:
            p, pool = max(pools, key=lambda x: x[0])
            high_p, high_price = max(highs, key=lambda x: x[0])
            active.append({'state': 'WAIT_MSS', 'sweep_i': i, 'pool_i': p, 'pool': pool,
                           'break_pivot_i': high_p, 'break_level': high_price})
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
    with (OUT / 'v376_trades.csv').open('w', newline='') as h:
        writer = csv.DictWriter(h, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    m = metrics(rows)
    gate = (m.get('n', 0) >= 300 and m.get('min_year_n', 0) >= 40 and m.get('wr', 0) >= 87 and
            m.get('avg_pnl', 0) >= 6.8 and m.get('min_year_wr', 0) >= 84 and m.get('micro_pct', 100) <= 1 and m.get('t1_violations', 1) == 0)
    report = {'version': 'V376_FULL_HISTORY_CAUSAL_60M_NEAREST_SWING_MSS_SERIAL_EXECUTION_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'confirmed 3/3 SSL sweep -> close breaks nearest prior confirmed swing high by 0.2% -> event-anchored bearish OB -> first touch -> reclaim -> hold -> next 60m open; one newest-sweep candidate per symbol/open and no overlapping positions; raw 60m only; T+1 exits',
              'source': {'v373_decision': source['decision'], 'hard_invalid_source_days': source['counts']['bad_slot_day_count'], 'all_invalid_days_are_excluded_by_per-day-bar-boundary': True},
              'metrics': m, 'production_gate': {'n>=300': m.get('n',0)>=300, 'min_year_n>=40':m.get('min_year_n',0)>=40, 'wr>=87':m.get('wr',0)>=87, 'avg>=6.8':m.get('avg_pnl',0)>=6.8, 'year_wr>=84':m.get('min_year_wr',0)>=84, 'micro<=1':m.get('micro_pct',100)<=1, 't1==0':m.get('t1_violations',1)==0},
              'decision': 'RESEARCH_CANDIDATE_ONLY__INDEPENDENT_SEMANTIC_ORACLE_REQUIRED' if gate else 'NO_PRODUCTION_PASS__CAUSAL_GENERATOR_CLOSED_OR_REVISE_SEMANTICS',
              'artifacts': {'trades': str(OUT / 'v376_trades.csv'), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2); (OUT / 'v376_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
