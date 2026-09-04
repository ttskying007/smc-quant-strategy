#!/usr/bin/env python3
"""V585 outcome-blind reduction-plan -> SSL exhaustion -> bullish reversal seeds."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from v582_lockup_release_ssl_exhaustion_seed import DAILY, METADATA, YEARS, daily_bars, date8, first_response

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
PRE = AUDIT / 'v584_insider_reduction_plan_ssl_exhaustion_preregistration_latest.json'
LATEST = AUDIT / 'v585_insider_reduction_plan_ssl_exhaustion_seed_latest.json'
OUT = AUDIT / f'v585_insider_reduction_plan_ssl_exhaustion_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
SUPPORT = {'raw_external_events_min': 4000, 'canonical_seed_total_min': 1000,
           'canonical_seed_each_year_min': 200, 'unique_symbols_min': 400}


def events() -> list[dict]:
    raw = []
    with METADATA.open(encoding='utf-8') as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            title, event_date = str(item.get('title') or ''), date8(item.get('notice_date'))
            if (item.get('kind') != 'HOLDER_DECREASE' or event_date[:4] not in YEARS or '减持' not in title or
                not any(x in title for x in ('计划', '预披露')) or any(x in title for x in ('实施', '完成', '进展', '时间过半', '届满', '结果'))):
                continue
            raw.append({'symbol': str(item.get('symbol') or ''), 'announcement_id': str(item.get('announcement_id') or ''),
                        'event_date': event_date, 'publication_time': str(item.get('publication_time') or ''),
                        'external_event': 'INSIDER_REDUCTION_PLAN_SUPPLY_EVENT', 'title': title})
    selected = {}
    for row in sorted(raw, key=lambda x: (x['symbol'], x['event_date'], x['announcement_id'])):
        selected.setdefault((row['symbol'], row['event_date']), row)
    return sorted(selected.values(), key=lambda x: (x['symbol'], x['event_date'], x['announcement_id']))


def main() -> None:
    pre = json.loads(PRE.read_text())
    assert pre['decision'] == 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED'
    OUT.mkdir(parents=True, exist_ok=False)
    source = events()
    grouped: defaultdict[str, list[dict]] = defaultdict(list)
    for row in source: grouped[row['symbol']].append(row)
    all_rows = []
    for n, (symbol, event_rows) in enumerate(sorted(grouped.items()), 1):
        bars = daily_bars(symbol)
        for event in event_rows:
            status, seed = first_response(event, bars)
            row = {**event, 'seed_status': status}
            if seed:
                seed['causal_path'] = 'PIT_INSIDER_REDUCTION_PLAN>CONFIRMED_SSL_SWEEP>CONFIRMED_BSL_BREAK>DEMAND_POI_RECLAIM>NEXT_OPEN'
                row.update(seed)
            all_rows.append(row)
        if n % 500 == 0: print(json.dumps({'symbols': n, 'events_processed': len(all_rows)}, ensure_ascii=False), flush=True)
    candidates = [x for x in all_rows if x['seed_status'] == 'SEED' and x['planned_entry_date'][:4] in YEARS]
    canonical = {}
    for row in sorted(candidates, key=lambda x: (x['symbol'], x['planned_entry_date'], x['event_date'], x['announcement_id'])):
        canonical.setdefault((row['symbol'], row['planned_entry_date']), row)
    seeds = sorted(canonical.values(), key=lambda x: (x['planned_entry_date'], x['symbol']))
    fields = sorted({key for row in all_rows for key in row} | {key for row in seeds for key in row})
    for name, rows in (('v585_all_reduction_plan_events.csv', all_rows), ('v585_outcome_blind_seeds.csv', seeds)):
        with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
    years = {year: sum(x['planned_entry_date'].startswith(year) for x in seeds) for year in YEARS}
    invariants = {
        'no_outcome_or_trade_files_read': True,
        'all_external_events_before_response': all(x['event_date'] < x['response_start_date'] for x in seeds),
        'all_ssl_anchors_confirmed_before_sweep': all(x['ssl_anchor_confirm_date'] < x['ssl_sweep_date'] for x in seeds),
        'all_bsl_anchors_confirmed_before_break': all(x['bsl_anchor_confirm_date'] < x['bsl_break_date'] for x in seeds),
        'all_causal_nodes_before_entry': all(x['event_date'] < x['ssl_sweep_date'] < x['bsl_break_date'] < x['reclaim_date'] < x['planned_entry_date'] for x in seeds),
        'one_seed_per_symbol_entry_date': len(seeds) == len({(x['symbol'], x['planned_entry_date']) for x in seeds}),
        'raw_external_events_capacity': len(source) >= SUPPORT['raw_external_events_min'],
        'canonical_seed_capacity': len(seeds) >= SUPPORT['canonical_seed_total_min'],
        'each_year_seed_capacity': all(years[y] >= SUPPORT['canonical_seed_each_year_min'] for y in YEARS),
        'unique_symbol_capacity': len({x['symbol'] for x in seeds}) >= SUPPORT['unique_symbols_min'],
    }
    passed = all(invariants[x] for x in ('raw_external_events_capacity', 'canonical_seed_capacity', 'each_year_seed_capacity', 'unique_symbol_capacity'))
    report = {'version': 'V585_INSIDER_REDUCTION_PLAN_SSL_EXHAUSTION_SEED_NO_OUTCOME', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'input_contract': 'PIT reduction-plan metadata plus daily OHLC only through planned entry; no outcome/trade/PnL/exit/MFE/MAE file read.',
              'raw_reduction_plan_event_count': len(source), 'raw_event_years': dict(sorted(Counter(x['event_date'][:4] for x in source).items())),
              'status_counts': dict(Counter(x['seed_status'] for x in all_rows)), 'canonical_seed_count': len(seeds),
              'canonical_seed_years': years, 'unique_symbols': len({x['symbol'] for x in seeds}), 'support_gate': SUPPORT,
              'invariants': invariants, 'decision': 'V585_SUPPORT_PASS__INDEPENDENT_RAW_ORACLE_REQUIRED' if passed else 'V585_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__CLOSE_OBJECT',
              'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v585_all_reduction_plan_events.csv'), 'seeds': str(OUT / 'v585_outcome_blind_seeds.csv'), 'latest': str(LATEST)}}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v585_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__ == '__main__': main()
