#!/usr/bin/env python3
"""V564 independent raw-bar oracle for V563; outcome data is never opened."""
from __future__ import annotations

import csv
import gzip
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
AUDIT = ROOT / 'smc_audit'
SEED_REPORT = AUDIT / 'v563_ssl_industry_expansion_midday_seed_latest.json'
INDUSTRY = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
OUT = AUDIT / f'v564_v563_independent_raw_oracle_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v564_v563_independent_raw_oracle_latest.json'


def n(value):
    try:
        value = float(value)
        return value if value > 0 and math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def unpack(path):
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def name(path, frame):
    return path.name[:-len(f'_{frame}.json.gz')].replace('_', '.')


def daily_bars(path):
    rows = []
    for raw in unpack(path):
        d = str(raw.get('d') or raw.get('t') or '')[:8]
        values = [n(raw.get(k)) for k in ('o', 'h', 'l', 'c', 'v')]
        if d and all(value is not None for value in values):
            rows.append(dict(zip(('d', 'o', 'h', 'l', 'c', 'v'), (d, *values))))
    return sorted(rows, key=lambda row: row['d'])


def pivot_low(rows, p):
    return (p >= 3 and p + 3 < len(rows) and
            rows[p]['l'] < min(rows[x]['l'] for x in range(p - 3, p)) and
            rows[p]['l'] <= min(rows[x]['l'] for x in range(p + 1, p + 4)))


def rebuild_daily(path):
    symbol, rows, result = name(path, 'daily'), daily_bars(path), []
    # The p+3 right confirmation exists before the subsequent sweep p+4 or later.
    for s in range(4, len(rows) - 1):
        p = s - 4
        if not pivot_low(rows, p):
            continue
        if rows[s]['l'] <= rows[p]['l'] * 0.997 and rows[s]['c'] > rows[p]['l']:
            result.append((symbol, rows[p]['d'], rows[s]['d'], rows[s + 1]['d']))
    return result


def session_features(path, wanted, industry):
    symbol, by_day = name(path, 'm15'), defaultdict(list)
    for raw in unpack(path):
        d = str(raw.get('d') or raw.get('t') or '')[:8]
        if d in wanted:
            by_day[d].append(raw)
    output = []
    for d, bars in by_day.items():
        bars.sort(key=lambda row: str(row.get('t') or ''))
        if len(bars) != 16:
            continue
        first, next_bar = bars[:8], bars[8]
        o, c, entry_open = n(first[0].get('o')), n(first[-1].get('c')), n(next_bar.get('o'))
        lows = [n(row.get('l')) for row in first]
        if o is None or c is None or entry_open is None or any(value is None for value in lows):
            continue
        output.append((symbol, industry, d, (c / o - 1) * 100, (min(lows) / o - 1) * 100,
                       str(first[-1].get('t') or ''), str(next_bar.get('t') or '')))
    return output


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    seed_report = json.loads(SEED_REPORT.read_text())
    with Path(seed_report['artifacts']['seeds']).open(newline='', encoding='utf-8') as handle:
        expected_rows = list(csv.DictReader(handle))
    expected = {row['causal_identity'] for row in expected_rows}
    industries = {str(row['symbol']): str(row.get('industry') or 'UNKNOWN').strip() or 'UNKNOWN'
                  for row in json.loads(INDUSTRY.read_text()) if row.get('symbol')}

    daily_events = []
    for index, path in enumerate(sorted((RAW / 'daily').glob('*_daily.json.gz')), 1):
        daily_events.extend(rebuild_daily(path))
        if index % 1000 == 0:
            print(json.dumps({'daily_oracle_files': index, 'events': len(daily_events)}), flush=True)
    wanted = {entry for _, _, _, entry in daily_events if entry[:4] in ('2025', '2026')}

    feature_map, industry_members = {}, defaultdict(list)
    for index, path in enumerate(sorted((RAW / 'm15').glob('*_m15.json.gz')), 1):
        symbol = name(path, 'm15')
        for feature in session_features(path, wanted, industries.get(symbol, 'UNKNOWN')):
            feature_map[(feature[0], feature[2])] = feature
            if feature[1] != 'UNKNOWN':
                industry_members[(feature[2], feature[1])].append(feature)
        if index % 1000 == 0:
            print(json.dumps({'m15_oracle_files': index, 'features': len(feature_map)}), flush=True)

    industry_stats = {}
    for key, members in industry_members.items():
        if len(members) >= 5:
            returns = [row[3] for row in members]
            industry_stats[key] = (median(returns), 100 * sum(value >= 0 for value in returns) / len(returns))

    oracle = set()
    traces = []
    for symbol, pivot_date, sweep_date, entry_date in daily_events:
        if entry_date[:4] not in ('2025', '2026'):
            continue
        feature = feature_map.get((symbol, entry_date))
        stat = industry_stats.get((entry_date, industries.get(symbol, 'UNKNOWN')))
        if feature is None or stat is None:
            continue
        stock_return, stock_dd, end_time, entry_time = feature[3], feature[4], feature[5], feature[6]
        sector_return, sector_up = stat
        if sector_return >= 0 and sector_up >= 50 and stock_return >= 0 and stock_dd >= -1.5:
            identity = f'{symbol}|{sweep_date}|{entry_date}'
            oracle.add(identity)
            traces.append({'causal_identity': identity, 'pivot_date': pivot_date, 'sweep_date': sweep_date,
                           'entry_date': entry_date, 'first120_end': end_time, 'entry_time': entry_time,
                           'industry_ret': round(sector_return, 6), 'industry_up_pct': round(sector_up, 6),
                           'stock_ret': round(stock_return, 6), 'stock_dd': round(stock_dd, 6)})
    missing, extra = sorted(expected - oracle), sorted(oracle - expected)
    chronology = all(row['pivot_date'] < row['sweep_date'] < row['entry_date'] and row['first120_end'] < row['entry_time'] for row in traces)
    trace_path = OUT / 'v564_raw_oracle_identities.csv'
    with trace_path.open('w', newline='', encoding='utf-8') as handle:
        fields = list(traces[0]) if traces else ['causal_identity']
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(traces)
    report = {
        'version': 'V564_V563_INDEPENDENT_RAW_ORACLE_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'input_contract': 'V563 expected identities plus raw Sina daily/M15 bars and static industry mapping only; no outcome/replay/exit file opened.',
        'independent_rebuild': 'direct raw scans independently reconstruct daily 3L/3R SSL reclaim, next-session 16-bar M15 first120 features, sector median/breadth expansion, and stock participation.',
        'expected_identities': len(expected), 'oracle_identities': len(oracle), 'missing': len(missing), 'extra': len(extra),
        'chronology_valid': chronology,
        'identity_match': not missing and not extra,
        'decision': 'V564_ORACLE_PASS__ONE_FROZEN_T1_REPLAY_AUTHORIZED' if not missing and not extra and chronology else 'V564_ORACLE_FAIL__NO_REPLAY_AUTHORIZED',
        'artifacts': {'out_dir': str(OUT), 'oracle_identities': str(trace_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v564_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
