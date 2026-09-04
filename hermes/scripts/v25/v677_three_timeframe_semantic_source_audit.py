#!/usr/bin/env python3
"""V677 no-write W/D/60m pure-SMC source and semantic audit.

Source contract: Sina 60m -> V379 raw daily -> ISO-week aggregation.  No trade,
entry, exit, return, SL/TP, indicator, or outcome field is read or emitted.
Every primitive is reset at an explicit V379 segment boundary.  Two independent
implementations produce timestamped primitive identities for differential audit.
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
M60 = ROOT / 'intraday_cache/sina_m60_v1'
DAILY = ROOT / 'intraday_cache/sina_raw_daily_v379'
AUDIT = ROOT / 'smc_audit'
V379 = AUDIT / 'v379_sina_m60_raw_daily_data_gate_latest.json'
START, END = '20230101', '20260710'
SLOTS = ('10:30:00', '11:30:00', '14:00:00', '15:00:00')
LEFT = RIGHT = 3
OUT = AUDIT / f'v677_three_timeframe_semantic_source_audit_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v677_three_timeframe_semantic_source_audit_latest.json'


def number(value: object) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else 0.0
    except (TypeError, ValueError):
        return 0.0


def read_gz(path: Path) -> list[dict]:
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise ValueError('not_list')
    return value


def daily_rows(path: Path) -> list[dict]:
    rows = []
    for raw in read_gz(path):
        t = str(raw.get('t', ''))[:8]
        o, h, l, c = (number(raw.get(k)) for k in ('o', 'h', 'l', 'c'))
        if START <= t <= END and min(o, h, l, c) > 0:
            rows.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'v': number(raw.get('v')), 'segment': int(raw.get('segment_id', 0))})
    return sorted(rows, key=lambda x: x['t'])


def m60_rows(path: Path, daily_by_date: dict[str, int]) -> tuple[list[dict], list[str]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for raw in read_gz(path):
        stamp = str(raw.get('day', ''))
        date = stamp[:10].replace('-', '')
        if date not in daily_by_date:
            continue
        o, h, l, c = (number(raw.get(k)) for k in ('open', 'high', 'low', 'close'))
        if min(o, h, l, c) <= 0:
            continue
        groups[date].append({'t': stamp, 'o': o, 'h': h, 'l': l, 'c': c, 'v': number(raw.get('volume'))})
    good, bad = [], []
    for date in sorted(daily_by_date):
        bars = sorted(groups.get(date, []), key=lambda x: x['t'])
        if len(bars) != 4 or tuple(x['t'][-8:] for x in bars) != SLOTS:
            bad.append(date)
            continue
        for bar in bars:
            bar['segment'] = daily_by_date[date]
        good.extend(bars)
    return good, bad


def aggregate_daily_from_m60(bars: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for bar in bars:
        groups[bar['t'][:10].replace('-', '')].append(bar)
    out = []
    for date, rows in sorted(groups.items()):
        rows.sort(key=lambda x: x['t'])
        if len(rows) == 4:
            out.append({'t': date, 'o': rows[0]['o'], 'h': max(x['h'] for x in rows), 'l': min(x['l'] for x in rows), 'c': rows[-1]['c'], 'v': sum(x['v'] for x in rows)})
    return out


def weekly_rows(daily: list[dict]) -> list[dict]:
    """Aggregate only continuous same-segment daily bars; ISO weeks do not bridge a quarantine."""
    buckets: list[list[dict]] = []
    current: list[dict] = []
    prior_key = prior_segment = None
    for bar in daily:
        iso = datetime.strptime(bar['t'], '%Y%m%d').isocalendar()
        key = (iso.year, iso.week)
        if current and (key != prior_key or bar['segment'] != prior_segment):
            buckets.append(current); current = []
        current.append(bar); prior_key, prior_segment = key, bar['segment']
    if current:
        buckets.append(current)
    return [{'t': g[-1]['t'], 'o': g[0]['o'], 'h': max(x['h'] for x in g), 'l': min(x['l'] for x in g), 'c': g[-1]['c'], 'v': sum(x['v'] for x in g), 'segment': g[0]['segment']} for g in buckets]


def contiguous_segments(rows: list[dict]) -> list[tuple[int, int]]:
    out, start = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i]['segment'] != rows[start]['segment']:
            out.append((start, i)); start = i
    return out


def primitives_a(rows: list[dict], frame: str) -> set[tuple]:
    """Reference scan: pivot confirmation -> one-time close breaks -> wick/reclaim sweeps -> event-anchored OB."""
    out: set[tuple] = set()
    for start, stop in contiguous_segments(rows):
        highs, lows, broken_h, broken_l = [], [], set(), set()
        for i in range(start + LEFT, stop - RIGHT):
            if all(rows[i]['h'] > rows[j]['h'] for j in range(i - LEFT, i + RIGHT + 1) if j != i):
                highs.append((i, i + RIGHT, rows[i]['h'])); out.add((frame, 'PIVOT_H', rows[i]['t'], rows[i + RIGHT]['t'], round(rows[i]['h'], 8)))
            if all(rows[i]['l'] < rows[j]['l'] for j in range(i - LEFT, i + RIGHT + 1) if j != i):
                lows.append((i, i + RIGHT, rows[i]['l'])); out.add((frame, 'PIVOT_L', rows[i]['t'], rows[i + RIGHT]['t'], round(rows[i]['l'], 8)))
        for i in range(start, stop):
            visible_h = [x for x in highs if x[1] <= i and x[0] not in broken_h]
            visible_l = [x for x in lows if x[1] <= i and x[0] not in broken_l]
            for pivot, kind in ((max(visible_h, default=None, key=lambda x: x[0]), 'BULL_BREAK'), (max(visible_l, default=None, key=lambda x: x[0]), 'BEAR_BREAK')):
                if pivot is None:
                    continue
                crossed = rows[i]['c'] > pivot[2] if kind == 'BULL_BREAK' else rows[i]['c'] < pivot[2]
                if not crossed:
                    continue
                (broken_h if kind == 'BULL_BREAK' else broken_l).add(pivot[0])
                out.add((frame, kind, rows[i]['t'], rows[pivot[0]]['t'], round(pivot[2], 8)))
                if kind == 'BULL_BREAK':
                    ob = next((j for j in range(i - 1, start - 1, -1) if rows[j]['c'] < rows[j]['o']), None)
                    if ob is not None:
                        out.add((frame, 'BULL_EVENT_OB', rows[i]['t'], rows[ob]['t'], round(rows[ob]['l'], 8), round(rows[ob]['h'], 8)))
            for pivot in visible_l:
                if rows[i]['l'] < pivot[2] and rows[i]['c'] > pivot[2]:
                    out.add((frame, 'SSL_SWEEP_RECLAIM', rows[i]['t'], rows[pivot[0]]['t'], round(pivot[2], 8)))
            for pivot in visible_h:
                if rows[i]['h'] > pivot[2] and rows[i]['c'] < pivot[2]:
                    out.add((frame, 'BSL_SWEEP_RECLAIM', rows[i]['t'], rows[pivot[0]]['t'], round(pivot[2], 8)))
    return out


def primitives_b(rows: list[dict], frame: str) -> set[tuple]:
    """Independent formulation: build confirmed pivot maps first, then evaluate each completed bar."""
    events: set[tuple] = set()
    for begin, end in contiguous_segments(rows):
        by_confirm_h: dict[int, list[tuple[int, float]]] = defaultdict(list)
        by_confirm_l: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for pivot in range(begin + LEFT, end - RIGHT):
            hwin = [rows[j]['h'] for j in range(pivot - LEFT, pivot + RIGHT + 1)]
            lwin = [rows[j]['l'] for j in range(pivot - LEFT, pivot + RIGHT + 1)]
            confirm = pivot + RIGHT
            if rows[pivot]['h'] == max(hwin) and hwin.count(rows[pivot]['h']) == 1:
                by_confirm_h[confirm].append((pivot, rows[pivot]['h'])); events.add((frame, 'PIVOT_H', rows[pivot]['t'], rows[confirm]['t'], round(rows[pivot]['h'], 8)))
            if rows[pivot]['l'] == min(lwin) and lwin.count(rows[pivot]['l']) == 1:
                by_confirm_l[confirm].append((pivot, rows[pivot]['l'])); events.add((frame, 'PIVOT_L', rows[pivot]['t'], rows[confirm]['t'], round(rows[pivot]['l'], 8)))
        active_h, active_l, used_h, used_l = [], [], set(), set()
        for now in range(begin, end):
            active_h.extend(by_confirm_h.get(now, [])); active_l.extend(by_confirm_l.get(now, []))
            # Match the causal contract exactly: only the most recently formed,
            # still-unbroken confirmed pivot may be the structure reference now.
            available_h = [(pivot, price) for pivot, price in active_h if pivot not in used_h]
            available_l = [(pivot, price) for pivot, price in active_l if pivot not in used_l]
            pivot_h = max(available_h, default=None, key=lambda x: x[0])
            if pivot_h is not None and rows[now]['c'] > pivot_h[1]:
                pivot, price = pivot_h
                used_h.add(pivot); events.add((frame, 'BULL_BREAK', rows[now]['t'], rows[pivot]['t'], round(price, 8)))
                for prior in range(now - 1, begin - 1, -1):
                    if rows[prior]['o'] > rows[prior]['c']:
                        events.add((frame, 'BULL_EVENT_OB', rows[now]['t'], rows[prior]['t'], round(rows[prior]['l'], 8), round(rows[prior]['h'], 8))); break
            pivot_l = max(available_l, default=None, key=lambda x: x[0])
            if pivot_l is not None and rows[now]['c'] < pivot_l[1]:
                pivot, price = pivot_l
                used_l.add(pivot); events.add((frame, 'BEAR_BREAK', rows[now]['t'], rows[pivot]['t'], round(price, 8)))
            # A sweep can only raid a still-available liquidity pool.  A pivot
            # consumed by a prior close-break is not a later sweep reference.
            for pivot, price in active_l:
                if pivot not in used_l and rows[now]['l'] < price < rows[now]['c']:
                    events.add((frame, 'SSL_SWEEP_RECLAIM', rows[now]['t'], rows[pivot]['t'], round(price, 8)))
            for pivot, price in active_h:
                if pivot not in used_h and rows[now]['h'] > price > rows[now]['c']:
                    events.add((frame, 'BSL_SWEEP_RECLAIM', rows[now]['t'], rows[pivot]['t'], round(price, 8)))
    return events


def symbol_from_path(path: Path) -> str:
    return path.name.replace('_raw_daily.json.gz', '').replace('_', '.')


def main() -> None:
    v379 = json.loads(V379.read_text())
    if v379.get('decision') != 'DATA_GATE_PASS__RAW_DAILY_SEMANTIC_ORACLE_ALLOWED':
        raise SystemExit('V379 source gate is not passed')
    OUT.mkdir(parents=True, exist_ok=False)
    totals, failures, mismatch_samples = Counter(), [], []
    csv_path = OUT / 'v677_symbol_source_and_semantic_rows.csv'
    fields = ['symbol', 'status', 'daily_rows', 'm60_rows', 'weekly_rows', 'm60_bad_days', 'daily_exact_match', 'm60_primitives', 'daily_primitives', 'weekly_primitives', 'mismatch_count']
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for idx, path in enumerate(sorted(DAILY.glob('*_raw_daily.json.gz')), 1):
            symbol = symbol_from_path(path); totals['symbols_seen'] += 1
            try:
                daily = daily_rows(path)
                code, exchange = symbol.split('.')
                m60, bad_days = m60_rows(M60 / f'{code}_{exchange}_m60_sina.json.gz', {x['t']: x['segment'] for x in daily})
                rebuilt = aggregate_daily_from_m60(m60)
                expected = [{k: x[k] for k in ('t', 'o', 'h', 'l', 'c', 'v')} for x in daily if x['t'] not in set(bad_days)]
                exact = len(rebuilt) == len(expected) and all(a == b for a, b in zip(rebuilt, expected))
                if not exact:
                    raise ValueError('m60_daily_aggregation_mismatch')
                weekly = weekly_rows(daily)
                sets = {'m60': primitives_a(m60, 'M60'), 'daily': primitives_a(daily, 'D'), 'weekly': primitives_a(weekly, 'W')}
                alt = {'m60': primitives_b(m60, 'M60'), 'daily': primitives_b(daily, 'D'), 'weekly': primitives_b(weekly, 'W')}
                diff = sum(len(sets[k] ^ alt[k]) for k in sets)
                if diff:
                    for frame in sets:
                        for event in sorted(sets[frame] ^ alt[frame])[:5]:
                            mismatch_samples.append({'symbol': symbol, 'frame': frame, 'event': event})
                totals['symbols_passed'] += 1; totals['m60_bad_days'] += len(bad_days); totals['mismatch_total'] += diff
                for frame in sets:
                    totals[f'{frame}_primitives'] += len(sets[frame])
                writer.writerow({'symbol': symbol, 'status': 'PASS' if diff == 0 else 'SEMANTIC_DIFFERENTIAL_FAIL', 'daily_rows': len(daily), 'm60_rows': len(m60), 'weekly_rows': len(weekly), 'm60_bad_days': len(bad_days), 'daily_exact_match': exact, 'm60_primitives': len(sets['m60']), 'daily_primitives': len(sets['daily']), 'weekly_primitives': len(sets['weekly']), 'mismatch_count': diff})
            except Exception as exc:
                totals['symbols_failed'] += 1; failures.append({'symbol': symbol, 'reason': f'{type(exc).__name__}:{exc}'})
                writer.writerow({'symbol': symbol, 'status': 'FAIL', 'daily_rows': '', 'm60_rows': '', 'weekly_rows': '', 'm60_bad_days': '', 'daily_exact_match': False, 'm60_primitives': '', 'daily_primitives': '', 'weekly_primitives': '', 'mismatch_count': ''})
            if idx % 250 == 0:
                print(f'V677 progress {idx}: pass={totals["symbols_passed"]} fail={totals["symbols_failed"]}', flush=True)
    decision = 'V677_SOURCE_AND_SEMANTIC_AUDIT_PASS__OUTCOME_BLIND_STATE_MACHINE_SEEDS_ALLOWED' if totals['symbols_failed'] == 0 and totals['mismatch_total'] == 0 else 'V677_SOURCE_OR_SEMANTIC_AUDIT_FAIL__STOP_BEFORE_SEEDS'
    report = {'version': 'V677_THREE_TIMEFRAME_SEMANTIC_SOURCE_AUDIT_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'source_contract': 'Sina raw 60m only; V379 raw daily is exact four-slot aggregation; weekly is same-source ISO-week aggregation reset at V379 segment boundaries.', 'semantic_contract': {'pivot': 'strict 3-left/3-right confirmed pivot, usable only at pivot+3', 'break': 'completed-bar close crosses a previously confirmed pivot', 'sweep': 'completed-bar wick pierces a previously confirmed pivot and closes back through it', 'ob': 'nearest prior opposite candle searched backward from a bull break; event-anchored only'}, 'forbidden_fields': ['entry', 'exit', 'pnl', 'return', 'SL', 'TP', 'MFE', 'MAE', 'indicator', 'outcome'], 'input': {'v379_decision': v379.get('decision'), 'range': v379.get('range'), 'daily_files': len(list(DAILY.glob('*_raw_daily.json.gz')))}, 'counts': dict(totals), 'failure_samples': failures[:100], 'mismatch_samples': mismatch_samples[:100], 'decision': decision, 'artifacts': {'symbol_rows': str(csv_path), 'report': str(OUT / 'v677_report.json'), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v677_report.json').write_text(text, encoding='utf-8'); LATEST.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
