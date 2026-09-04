#!/usr/bin/env python3
"""V392 no-write disclosure-event window robustness audit.

A single 20-calendar-day PIT fetch is made for each V381 hold-time/symbol. The
predeclared nested windows 1/3/5/10/20 days are then only *reported*; no window
is selected or promoted by this script. Provider publication time must lie
inside each candidate's exact lower/upper bound.
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
OUT = AUD / f'v392_pit_disclosure_window_robustness_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v392_pit_disclosure_window_robustness_latest.json'
URL = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
WINDOWS = (1, 3, 5, 10, 20)
CHUNK_SIZE = 200
SCHEMA = {
    'REGULATORY_OR_NEGATIVE': ('立案', '处罚', '问询函', '监管', '风险提示', '终止', '亏损', '预亏', '减持', '冻结', '诉讼', '仲裁', '退市'),
    'CAPITAL_RETURN_OR_INCREASE': ('回购', '增持', '分红', '权益分派'),
    'FUNDAMENTAL_POSITIVE': ('业绩预增', '业绩快报', '业绩预告', '经营情况', '年度报告', '半年度报告', '季度报告'),
    'BUSINESS_POSITIVE': ('中标', '合同', '订单', '签署', '合作', '项目'),
}


def stamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None


def code(symbol: str) -> str:
    return symbol.split('.', 1)[0]


def classify(title: str) -> str:
    for state, terms in SCHEMA.items():
        if any(term in title for term in terms):
            return state
    return 'OTHER_DISCLOSURE'


def fetch(session: requests.Session, codes: list[str], start: str, end: str) -> tuple[list[dict], str | None]:
    rows = []
    for page in range(1, 101):
        try:
            params = {'client_source': 'web', 'page_size': 100, 'page_index': page, 'ann_type': 'A',
                      'stock_list': ','.join(codes), 'begin_time': start, 'end_time': end}
            response = session.get(URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json().get('data') or {}
            batch = data.get('list') or []
            rows.extend(batch)
            if len(rows) >= int(data.get('total_hits') or 0) or not batch:
                return rows, None
            time.sleep(.03)
        except Exception as exc:
            return rows, f'{type(exc).__name__}:{exc}'
    return rows, 'PAGE_CAP_EXCEEDED'


def state_for(announcements: list[dict], cutoff: datetime, days: int) -> tuple[str, int, bool]:
    lower = cutoff - timedelta(days=days)
    eligible = [row for row in announcements if (published := stamp(row.get('eiTime', ''))) and lower <= published <= cutoff]
    states = [classify(row.get('title', '')) for row in eligible]
    state = next((name for name in SCHEMA if name in states), 'OTHER_DISCLOSURE' if states else 'NO_RECENT_DISCLOSURE')
    return state, len(eligible), all(lower <= stamp(row['eiTime']) <= cutoff for row in eligible)


def stats(rows: list[dict]) -> dict:
    pnl = [float(row['pnl_pct']) for row in rows]
    by_year: dict[str, list[float]] = defaultdict(list)
    for row, value in zip(rows, pnl):
        by_year[row['entry_date'][:4]].append(value)
    yearly = {year: {'n': len(values), 'wr': round(100 * sum(x > 0 for x in values) / len(values), 4),
                     'avg_pnl': round(sum(values) / len(values), 4)} for year, values in sorted(by_year.items())}
    return {'n': len(rows), 'wr': round(100 * sum(value > 0 for value in pnl) / len(pnl), 4) if pnl else 0,
            'avg_pnl': round(sum(pnl) / len(pnl), 4) if pnl else 0,
            'sl_pct': round(100 * sum(row['exit_reason'] == 'SL_HIT' for row in rows) / len(rows), 4) if rows else 0,
            'yearly': yearly, 'min_year_n': min((item['n'] for item in yearly.values()), default=0),
            'min_year_wr': min((item['wr'] for item in yearly.values()), default=0)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = json.loads(V381.read_text())
    with Path(base['artifacts']['trades']).open(newline='') as handle:
        trades = list(csv.DictReader(handle))
    targets = sorted(set((row['symbol'], row['hold_time']) for row in trades))
    by_day: dict[str, set[str]] = defaultdict(set)
    for symbol, hold_time in targets:
        by_day[hold_time[:10]].add(symbol)
    session = requests.Session(); session.headers.update(HEADERS)
    fetched: dict[str, list[dict]] = defaultdict(list)
    failures = []; query_count = 0
    for day, symbols in sorted(by_day.items()):
        end = datetime.strptime(day, '%Y-%m-%d').date()
        start = end - timedelta(days=max(WINDOWS))
        items = sorted(symbols)
        for offset in range(0, len(items), CHUNK_SIZE):
            rows, error = fetch(session, [code(symbol) for symbol in items[offset:offset + CHUNK_SIZE]], start.isoformat(), end.isoformat())
            query_count += 1
            if error:
                failures.append({'day': day, 'count': len(items[offset:offset + CHUNK_SIZE]), 'error': error})
                continue
            for row in rows:
                for item in row.get('codes') or []:
                    if item.get('stock_code'):
                        fetched[item['stock_code']].append(row)
            time.sleep(.04)
    feature_rows = []
    for symbol, hold_time in targets:
        cutoff = stamp(hold_time)
        anns = fetched.get(code(symbol), [])
        item = {'symbol': symbol, 'hold_time': hold_time, 'feature_cutoff': hold_time}
        for days in WINDOWS:
            state, count, inside = state_for(anns, cutoff, days)
            item[f'state_{days}d'] = state
            item[f'announcement_count_{days}d'] = count
            item[f'exact_window_{days}d'] = inside
        feature_rows.append(item)
    feature_map = {(row['symbol'], row['hold_time']): row for row in feature_rows}
    joined = [{**trade, **feature_map[(trade['symbol'], trade['hold_time'])]} for trade in trades]
    baseline = stats(joined)
    windows = {}
    for days in WINDOWS:
        column = f'state_{days}d'
        buckets = {state: stats([row for row in joined if row[column] == state]) for state in sorted({row[column] for row in joined})}
        fundamental = buckets.get('FUNDAMENTAL_POSITIVE', {'n': 0, 'wr': 0, 'avg_pnl': 0, 'min_year_n': 0, 'min_year_wr': 0})
        windows[str(days)] = {
            'state_counts': dict(Counter(row[column] for row in joined)),
            'fundamental_positive': fundamental,
            'fundamental_uplift': {'wr_pp': round(fundamental['wr'] - baseline['wr'], 4),
                                   'avg_pnl_pp': round(fundamental['avg_pnl'] - baseline['avg_pnl'], 4),
                                   'min_year_wr_pp': round(fundamental['min_year_wr'] - baseline['min_year_wr'], 4)},
            'all_states': buckets,
        }
    gate = {'all_target_features_built': len(feature_rows) == len(targets), 'all_queries_succeeded': not failures,
            'all_exact_bounds_enforced': all(row[f'exact_window_{days}d'] for row in feature_rows for days in WINDOWS),
            'outcome_fields_read_or_emitted_before_feature_build': False,
            'feature_cutoffs_equal_hold_time': all(row['feature_cutoff'] == row['hold_time'] for row in feature_rows)}
    with (OUT / 'v392_features.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(feature_rows[0])); writer.writeheader(); writer.writerows(feature_rows)
    result = {'version': 'V392_PIT_DISCLOSURE_WINDOW_ROBUSTNESS_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'predeclared nested 1/3/5/10/20 day PIT disclosure windows; event taxonomy fixed; results are robustness evidence only, never a fitted selection',
              'windows': list(WINDOWS), 'baseline': baseline, 'window_results': windows, 'gate': gate,
              'decision': 'WINDOW_ROBUSTNESS_READY_FOR_RESEARCH_INTERPRETATION' if all(gate.values()) else 'WINDOW_ROBUSTNESS_DATA_GATE_FAIL__STOP',
              'artifacts': {'features': str(OUT / 'v392_features.csv'), 'latest': str(LATEST)}, 'failure_samples': failures[:30]}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v392_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
