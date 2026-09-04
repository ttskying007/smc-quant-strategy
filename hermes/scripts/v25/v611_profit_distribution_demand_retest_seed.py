#!/usr/bin/env python3
"""V611: outcome-blind seeds for the frozen V610 profit-distribution ontology."""
from __future__ import annotations

import csv
import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT, DAILY = ROOT / 'smc_audit', ROOT / 'kline_cache'
CATALOG = AUDIT / 'v609_cash_dividend_plan_event_catalog_latest.json'
PRE = AUDIT / 'v610_profit_distribution_demand_retest_preregistration_latest.json'
LATEST = AUDIT / 'v611_profit_distribution_demand_retest_seed_latest.json'
OUT = AUDIT / f'v611_profit_distribution_demand_retest_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
YEARS = ('2023', '2024', '2025')
INCLUDE = ('利润分配预案', '现金分红预案', '利润分配方案')
EXCLUDE = ('实施', '权益分派', '除权除息', '调整', '更正', '终止', '进展', '结果', '完成', '法律意见书', '独立财务顾问', '征求投资者意见', '转增股本')


def d8(value: object) -> str:
    digits = ''.join(char for char in str(value or '') if char.isdigit())
    return digits[:8] if len(digits) >= 8 else ''


def positive(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def a_share(symbol: str) -> bool:
    return len(symbol) == 9 and symbol[6:] in ('.SH', '.SZ') and symbol[:6].startswith(('00', '30', '60', '68'))


def event_rows(catalog: dict) -> list[dict]:
    source, canonical = Path(catalog['artifacts']['events']), {}
    for line in source.open(encoding='utf-8'):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        symbol, event_date, title = str(item.get('symbol') or ''), d8(item.get('notice_date')), str(item.get('title') or '')
        eligible = (a_share(symbol) and event_date[:4] in YEARS and any(term in title for term in INCLUDE) and not any(term in title for term in EXCLUDE))
        if eligible:
            row = {
                'symbol': symbol,
                'announcement_id': str(item.get('announcement_id') or ''),
                'event_date': event_date,
                'publication_time': str(item.get('publication_time') or ''),
                'title': title,
                'matched_terms': '|'.join(item.get('matched_terms') or []),
                'external_event': 'PIT_PROFIT_DISTRIBUTION_PLAN',
            }
            canonical.setdefault((symbol, event_date), row)
    return sorted(canonical.values(), key=lambda row: (row['symbol'], row['event_date'], row['announcement_id']))


def bars(symbol: str) -> list[dict]:
    try:
        raw = json.loads((DAILY / f'{symbol.replace(".", "_")}_daily_750.json').read_text())
    except (OSError, ValueError):
        return []
    result = []
    for item in raw if isinstance(raw, list) else []:
        date = d8(item.get('t') or item.get('date'))
        values = [positive(item.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(date) == 8 and all(value is not None for value in values):
            result.append({'d': date, 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(result, key=lambda row: row['d'])


def confirmed_highs(rows: list[dict], end: int) -> list[tuple[int, int]]:
    result = []
    for index in range(3, end - 3):
        if rows[index]['h'] > max(row['h'] for row in rows[index - 3:index]) and rows[index]['h'] >= max(row['h'] for row in rows[index + 1:index + 4]):
            result.append((index, index + 3))
    return result


def seed_for(event: dict, rows: list[dict]) -> tuple[str, dict | None]:
    dates = [row['d'] for row in rows]
    start = bisect_right(dates, event['event_date'])
    if start >= len(rows):
        return 'NO_RESPONSE_SESSION', None
    for break_i in range(start, min(start + 30, len(rows))):
        known = [(i, confirmed) for i, confirmed in confirmed_highs(rows, break_i + 1) if confirmed < break_i and rows[i]['h'] < rows[break_i]['c']]
        if not known:
            continue
        bsl_i, bsl_confirm_i = known[-1]
        bearish = [i for i in range(start, break_i + 1) if rows[i]['c'] < rows[i]['o']]
        if not bearish:
            continue
        poi_i = bearish[-1]
        low, high = rows[poi_i]['l'], rows[poi_i]['o']
        for reclaim_i in range(break_i + 1, min(break_i + 16, len(rows))):
            bar = rows[reclaim_i]
            if bar['l'] <= high and bar['h'] >= low and bar['c'] >= high and reclaim_i + 1 < len(rows):
                entry_i = reclaim_i + 1
                return 'SEED', {
                    **event,
                    'response_start_date': rows[start]['d'],
                    'bsl_anchor_date': rows[bsl_i]['d'],
                    'bsl_anchor_confirm_date': rows[bsl_confirm_i]['d'],
                    'bsl_break_date': rows[break_i]['d'],
                    'poi_date': rows[poi_i]['d'],
                    'zone_low': round(low, 6),
                    'zone_high': round(high, 6),
                    'reclaim_date': rows[reclaim_i]['d'],
                    'planned_entry_date': rows[entry_i]['d'],
                    'causal_path': 'PIT_PROFIT_DISTRIBUTION_PLAN>CONFIRMED_BSL_ACCEPTANCE>DEMAND_OB_RETEST_RECLAIM>NEXT_OPEN',
                }
    return 'NO_COMPLETED_DEMAND_RETEST', None


def main() -> None:
    catalog, preregistration = json.loads(CATALOG.read_text()), json.loads(PRE.read_text())
    if catalog['decision'] != 'SOURCE_CATALOG_COMPLETE__SEMANTIC_PREREGISTRATION_NEXT' or preregistration['decision'] != 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED':
        raise RuntimeError('V609 catalog and V610 preregistration required')
    OUT.mkdir(parents=True, exist_ok=False)
    source, grouped, all_rows = event_rows(catalog), defaultdict(list), []
    for event in source:
        grouped[event['symbol']].append(event)
    for number, (symbol, events) in enumerate(sorted(grouped.items()), 1):
        stock_bars = bars(symbol)
        for event in events:
            status, seed = seed_for(event, stock_bars)
            all_rows.append({**event, 'seed_status': status, **(seed or {})})
        if number % 500 == 0:
            print(json.dumps({'symbols': number, 'events_processed': len(all_rows)}), flush=True)
    candidates = [row for row in all_rows if row['seed_status'] == 'SEED' and row['planned_entry_date'][:4] in YEARS]
    canonical = {}
    for row in sorted(candidates, key=lambda row: (row['symbol'], row['planned_entry_date'], row['event_date'], row['announcement_id'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda row: (row['planned_entry_date'], row['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, rows in [('v611_all_profit_distribution_events.csv', all_rows), ('v611_outcome_blind_seeds.csv', seeds)]:
        with (OUT / name).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
    years = {year: sum(row['planned_entry_date'].startswith(year) for row in seeds) for year in YEARS}
    checks = {'canonical_seed_total': len(seeds) >= 1000, 'canonical_seed_each_year': all(years[year] >= 300 for year in YEARS), 'unique_symbols': len({row['symbol'] for row in seeds}) >= 500}
    invariants = {
        'no_outcome_or_trade_files_read': True,
        'all_events_precede_response': all(row['event_date'] < row['response_start_date'] for row in seeds),
        'all_bsl_anchors_confirmed_before_break': all(row['bsl_anchor_confirm_date'] < row['bsl_break_date'] for row in seeds),
        'all_causal_nodes_before_entry': all(row['event_date'] < row['bsl_break_date'] < row['reclaim_date'] < row['planned_entry_date'] for row in seeds),
        'one_seed_per_symbol_entry_date': len(seeds) == len({(row['symbol'], row['planned_entry_date']) for row in seeds}),
    }
    passed = all(checks.values()) and all(invariants.values())
    report = {
        'version': 'V611_PROFIT_DISTRIBUTION_DEMAND_RETEST_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'V609 immutable profit-distribution metadata plus daily OHLC only through planned entry; no outcome/trade/PnL/exit/MFE/MAE file read.',
        'raw_canonical_event_count': len(source),
        'raw_canonical_event_years': {year: sum(row['event_date'].startswith(year) for row in source) for year in YEARS},
        'seed_status_counts': dict(Counter(row['seed_status'] for row in all_rows)),
        'canonical_seed_count': len(seeds),
        'canonical_seed_years': years,
        'unique_symbols': len({row['symbol'] for row in seeds}),
        'support_checks': checks,
        'invariants': invariants,
        'decision': 'V611_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if passed else 'V611_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_ONTOLOGY',
        'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v611_all_profit_distribution_events.csv'), 'seeds': str(OUT / 'v611_outcome_blind_seeds.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v611_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
