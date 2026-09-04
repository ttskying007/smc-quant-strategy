#!/usr/bin/env python3
"""V562 outcome-blind 2025-2026 research seed gate.

New strategy ontology (not a V543 threshold/exit variant):
completed weekly/daily bullish structure -> same-session industry leadership
and stock participation -> M15 absorption/reclaim -> next trading-day open.

Only V543's outcome-blind M15 identities and raw Sina OHLCV are read.  This
program never opens trade outcomes and never writes production state.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina'
V543 = AUDIT / 'v543_sina_m15_ssl_displacement_absorption_seed_gate_no_write_20260723_040005/v543_outcome_blind_seeds.csv'
INDUSTRY = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
OUT = AUDIT / f'v562_htf_industry_m15_absorption_seed_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v562_htf_industry_m15_absorption_seed_gate_latest.json'
YEARS = ('2025', '2026')
LEFT = RIGHT = 3
# Pre-outcome capacity gate: replay loses rows to target and serial-position rules.
SUPPORT = {'seed_total_min': 3000, 'seed_each_year_min': 1200, 'unique_symbols_min': 500}


def positive(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def load_gzip(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def daily_rows(symbol: str) -> list[dict[str, Any]]:
    path = RAW / 'daily' / f'{symbol.replace(".", "_")}_daily.json.gz'
    rows = []
    for raw in load_gzip(path):
        date = str(raw.get('d') or raw.get('t') or '')[:8]
        values = [positive(raw.get(key)) for key in ('o', 'h', 'l', 'c', 'v')]
        if len(date) == 8 and all(value is not None for value in values):
            rows.append(dict(d=date, o=values[0], h=values[1], l=values[2], c=values[3], v=values[4]))
    return sorted(rows, key=lambda row: row['d'])


def pivots(rows: list[dict[str, Any]]) -> tuple[list[tuple[int, int, float]], list[tuple[int, int, float]]]:
    lows, highs = [], []
    for index in range(LEFT, len(rows) - RIGHT):
        before, after = rows[index - LEFT:index], rows[index + 1:index + RIGHT + 1]
        if rows[index]['l'] < min(row['l'] for row in before) and rows[index]['l'] <= min(row['l'] for row in after):
            lows.append((index, index + RIGHT, rows[index]['l']))
        if rows[index]['h'] > max(row['h'] for row in before) and rows[index]['h'] >= max(row['h'] for row in after):
            highs.append((index, index + RIGHT, rows[index]['h']))
    return lows, highs


def completed_weeks(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    current = None
    for row in daily:
        week = datetime.strptime(row['d'], '%Y%m%d').date().isocalendar()[:2]
        if week != current:
            groups.append([])
            current = week
        groups[-1].append(row)
    return [dict(d=group[-1]['d'], o=group[0]['o'], h=max(row['h'] for row in group),
                 l=min(row['l'] for row in group), c=group[-1]['c'], v=sum(row['v'] for row in group))
            for group in groups[:-1] if group]


def completed_higher_low(rows: list[dict[str, Any]], asof: str) -> dict[str, str] | None:
    lows, _ = pivots(rows)
    confirmed = [item for item in lows if rows[item[1]]['d'] < asof]
    prior_rows = [row for row in rows if row['d'] < asof]
    if len(confirmed) < 2 or not prior_rows:
        return None
    prior, latest = confirmed[-2:]
    if latest[2] <= prior[2] or prior_rows[-1]['c'] <= latest[2]:
        return None
    return {'prior_hl_date': rows[prior[0]]['d'], 'latest_hl_date': rows[latest[0]]['d'],
            'confirm_date': rows[latest[1]]['d']}


def industry_map() -> dict[str, str]:
    try:
        rows = json.loads(INDUSTRY.read_text())
    except (OSError, ValueError):
        return {}
    return {str(row.get('symbol')): str(row.get('industry') or 'UNKNOWN')
            for row in rows if isinstance(row, dict) and row.get('symbol')}


def first120(symbol: str, wanted: set[str]) -> list[dict[str, Any]]:
    path = RAW / 'm15' / f'{symbol.replace(".", "_")}_m15.json.gz'
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in load_gzip(path):
        stamp = str(raw.get('t') or '')
        date = str(raw.get('d') or stamp[:8])[:8]
        if date in wanted and len(stamp) == 14:
            by_date[date].append(raw)
    output = []
    for date, bars in by_date.items():
        bars.sort(key=lambda row: str(row.get('t') or ''))
        if len(bars) != 16:
            continue
        first = bars[:8]
        o = positive(first[0].get('o'))
        c = positive(first[-1].get('c'))
        lows = [positive(bar.get('l')) for bar in first]
        if not o or not c or any(value is None for value in lows):
            continue
        amount = sum((positive(bar.get('v')) or 0) * (positive(bar.get('c')) or 0) for bar in first)
        output.append({'symbol': symbol, 'date': date, 'ret': (c / o - 1) * 100,
                       'low_dd': (min(lows) / o - 1) * 100, 'amount': amount})
    return output


def next_trade_day(dates: list[str], date: str) -> str | None:
    index = bisect_right(dates, date)
    return dates[index] if index < len(dates) else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=False)
    with V543.open(newline='', encoding='utf-8') as handle:
        base = [row for row in csv.DictReader(handle) if row['entry_date'][:4] in YEARS]
    symbols = sorted({row['symbol'] for row in base})
    wanted = {row['entry_date'] for row in base}
    wanted_by_symbol: dict[str, set[str]] = defaultdict(set)
    for row in base:
        wanted_by_symbol[row['symbol']].add(row['entry_date'])
    mapping = industry_map()

    daily_by_symbol = {symbol: daily_rows(symbol) for symbol in symbols}
    parent = {}
    for symbol, rows in daily_by_symbol.items():
        weekly = completed_weeks(rows)
        dates = [row['d'] for row in rows]
        date_set = set(dates)
        for date in wanted_by_symbol[symbol]:
            if not dates or date <= dates[0] or date not in date_set:
                continue
            weekly_state = completed_higher_low(weekly, date)
            daily_state = completed_higher_low(rows, date)
            execution_date = next_trade_day(dates, date)
            if weekly_state and daily_state and execution_date:
                parent[(symbol, date)] = {**weekly_state, **{f'daily_{k}': v for k, v in daily_state.items()},
                                          'execution_date': execution_date}

    features = []
    for position, symbol in enumerate(symbols, 1):
        for row in first120(symbol, wanted):
            row['industry'] = mapping.get(symbol, 'UNKNOWN')
            features.append(row)
        if position % 1000 == 0:
            print(json.dumps({'m15_symbols': position, 'features': len(features)}), flush=True)

    feature_by_id = {(row['symbol'], row['date']): row for row in features}
    by_industry: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in features:
        if row['industry'] != 'UNKNOWN':
            by_industry[(row['date'], row['industry'])].append(row)
    industry_stats = {}
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (date, industry), rows in by_industry.items():
        if len(rows) >= 5:
            stat = {'median_ret': median(row['ret'] for row in rows),
                    'up_pct': 100 * sum(row['ret'] >= 0 for row in rows) / len(rows),
                    'amount': sum(row['amount'] for row in rows), 'members': len(rows), 'industry': industry}
            industry_stats[(date, industry)] = stat
            by_date[date].append(stat)
    for date, rows in by_date.items():
        for rank, row in enumerate(sorted(rows, key=lambda x: x['median_ret'], reverse=True), 1):
            row['ret_rank_pct'] = 100 * rank / len(rows)
        for stat in rows:
            industry_stats[(date, stat['industry'])].update({'ret_rank_pct': stat['ret_rank_pct']})

    rows = []
    for seed in base:
        symbol, date = seed['symbol'], seed['entry_date']
        parent_state = parent.get((symbol, date))
        feature = feature_by_id.get((symbol, date))
        stat = industry_stats.get((date, mapping.get(symbol, 'UNKNOWN')))
        if not parent_state or not feature or not stat:
            continue
        # Leadership and participation are known by 11:30, while execution is next day open.
        if stat['ret_rank_pct'] > 40 or feature['ret'] < 0 or feature['low_dd'] <= -1.5:
            continue
        rows.append({'symbol': symbol, 'signal_date': date, 'execution_date': parent_state['execution_date'],
                     'm15_reclaim_time': seed['reclaim_time'], 'm15_entry_observed_time': seed['entry_time'],
                     'weekly_prior_hl_date': parent_state['prior_hl_date'], 'weekly_latest_hl_date': parent_state['latest_hl_date'],
                     'weekly_hl_confirm_date': parent_state['confirm_date'],
                     'daily_prior_hl_date': parent_state['daily_prior_hl_date'], 'daily_latest_hl_date': parent_state['daily_latest_hl_date'],
                     'daily_hl_confirm_date': parent_state['daily_confirm_date'],
                     'industry_ret_rank_pct': round(stat['ret_rank_pct'], 4), 'industry_first120_ret_pct': round(stat['median_ret'], 4),
                     'stock_first120_ret_pct': round(feature['ret'], 4), 'stock_first120_low_dd_pct': round(feature['low_dd'], 4),
                     'causal_sequence': 'completed_weekly_HL>completed_daily_HL>m15_absorption_reclaim>first120_industry_top40_and_stock_participation>next_trade_day_open'})
    rows.sort(key=lambda row: (row['signal_date'], row['symbol'], row['m15_reclaim_time']))
    dedup = {(row['symbol'], row['m15_reclaim_time']): row for row in rows}
    rows = sorted(dedup.values(), key=lambda row: (row['signal_date'], row['symbol'], row['m15_reclaim_time']))
    years = Counter(row['signal_date'][:4] for row in rows)
    invariant = {
        'source_isolated_sina_only': True,
        'all_parent_states_before_signal': all(row['weekly_hl_confirm_date'] < row['signal_date'] and row['daily_hl_confirm_date'] < row['signal_date'] for row in rows),
        'all_execution_next_trade_day': all(row['execution_date'] > row['signal_date'] for row in rows),
        'all_m15_reclaim_before_execution': all(row['m15_reclaim_time'][:8] <= row['signal_date'] < row['execution_date'] for row in rows),
        'no_outcome_fields': all(not any(banned in key.lower() for key in row for banned in ('pnl', 'return', 'exit', 'mae', 'mfe', 'target', 'stop')) for row in rows),
        'seed_total_capacity': len(rows) >= SUPPORT['seed_total_min'],
        'seed_each_year_capacity': all(years[year] >= SUPPORT['seed_each_year_min'] for year in YEARS),
        'unique_symbols_capacity': len({row['symbol'] for row in rows}) >= SUPPORT['unique_symbols_min'],
    }
    seed_path = OUT / 'v562_outcome_blind_seeds.csv'
    with seed_path.open('w', newline='', encoding='utf-8') as handle:
        fields = list(rows[0]) if rows else ['symbol', 'signal_date']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    report = {
        'version': 'V562_HTF_INDUSTRY_M15_ABSORPTION_SEED_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'SINA_SOURCE_ISOLATED_COMPLETE_2025_2026_PARTIAL_HISTORY__RESEARCH_ONLY',
        'hypothesis': 'A weekly-plus-daily confirmed higher-low parent state, paired with same-session top-40-percent industry first120 leadership and stock participation, identifies M15 absorption/reclaim events that can survive to next-day A-share execution.',
        'frozen_pre_outcome_contract': 'Use only completed weekly/daily 3L/3R higher lows strictly before the signal date; M15 absorption/reclaim identity from V543 outcome-blind source; first120 industry rank<=40 and stock return>=0 with drawdown>-1.5, then execute only at next available daily open. No outcomes read.',
        'predeclared_replay_gate': {'n_min': 1000, 'year_n_min': 300, 'wr_pct_min': 55.0, 'avg_net_pct_min': 0.5, 'pf_min': 1.15, 'payoff_min': 0.7, 'every_year_avg_net_positive': True, 't1_violations': 0},
        'support_gate_before_outcomes': SUPPORT, 'base_v543_outcome_blind_seeds_read': len(base), 'seed_count': len(rows), 'year_counts': dict(years), 'unique_symbols': len({row['symbol'] for row in rows}),
        'invariants': invariant,
        'decision': 'V562_SUPPORT_PASS__INDEPENDENT_ORACLE_REQUIRED' if all(invariant.values()) else 'V562_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
        'artifacts': {'out_dir': str(OUT), 'seeds': str(seed_path), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v562_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
