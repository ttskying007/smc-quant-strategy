#!/usr/bin/env python3
"""V565 outcome-blind generator for frozen V564 PIT commitment -> SMC response.

Reads only V563 announcement metadata and local daily OHLCV needed through the
planned entry. It does not open a trade, PnL, outcome, exit, MFE, or MAE file.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
CACHE = ROOT / 'kline_cache'
PRE = AUD / 'v564_pit_commitment_to_smc_ontology_preregistration_latest.json'
META = AUD / 'v563_pit_event_archive_full_coverage_no_outcome_20260724_124935' / 'v563_event_metadata.jsonl'
OUT = AUD / f'v565_pit_commitment_smc_response_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v565_pit_commitment_smc_response_seed_latest.json'

BUYBACK_EXCLUDE = re.compile(r'进展|实施结果|完成|期限届满|注销|减少注册资本|补偿股份|业绩承诺|终止|调整')
INCREASE_EXCLUDE = re.compile(r'减持|进展|完成|结果|实施|时间过半|解除|质押|权益变动|被动')
ACTOR = re.compile(r'控股股东|实际控制人|董事|监事|高级管理人员|持股5%以上|股东')


def f(x: object) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def selected_family(row: dict) -> str | None:
    title = str(row.get('title') or '')
    if (
        row.get('kind') == 'BUYBACK'
        and '回购' in title
        and re.search(r'方案|预案|董事会|股东大会', title)
        and not BUYBACK_EXCLUDE.search(title)
    ):
        return 'BUYBACK_INIT'
    if (
        row.get('kind') == 'HOLDER_INCREASE'
        and '增持' in title
        and re.search(r'计划|拟', title)
        and ACTOR.search(title)
        and not INCREASE_EXCLUDE.search(title)
    ):
        return 'INSIDER_INCREASE_INIT'
    return None


def load_events() -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for line in META.open(encoding='utf-8'):
        row = json.loads(line)
        family = selected_family(row)
        if not family:
            continue
        key = (family, str(row['symbol']), str(row['announcement_id']))
        if key in seen:
            continue
        seen.add(key)
        pub = str(row.get('publication_time') or '')[:10].replace('-', '')
        if len(pub) != 8 or not pub.isdigit():
            continue
        out.append({
            'family': family,
            'symbol': str(row['symbol']),
            'announcement_id': str(row['announcement_id']),
            'publication_date': pub,
            'event_year': pub[:4],
            'title': str(row['title']),
        })
    return sorted(out, key=lambda x: (x['symbol'], x['publication_date'], x['announcement_id']))


def load_bars(symbol: str) -> list[dict]:
    path = CACHE / f"{symbol.replace('.', '_')}_daily_750.json"
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    out: list[dict] = []
    for x in raw if isinstance(raw, list) else []:
        d = str(x.get('t') or x.get('date') or '')[:8]
        o, h, l, c = (f(x.get(k)) for k in ('o', 'h', 'l', 'c'))
        if len(d) == 8 and d.isdigit() and all(v is not None and v > 0 for v in (o, h, l, c)):
            out.append({'d': d, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(out, key=lambda x: x['d'])


def pivot_low(xs: list[dict], i: int) -> bool:
    return i >= 3 and i + 3 < len(xs) and xs[i]['l'] < min(x['l'] for x in xs[i-3:i]) and xs[i]['l'] <= min(x['l'] for x in xs[i+1:i+4])


def pivot_high(xs: list[dict], i: int) -> bool:
    return i >= 3 and i + 3 < len(xs) and xs[i]['h'] > max(x['h'] for x in xs[i-3:i]) and xs[i]['h'] >= max(x['h'] for x in xs[i+1:i+4])


def find_first_chain(event: dict, xs: list[dict]) -> tuple[str, dict | None]:
    # Publication-day trading is always forbidden: first index strictly after publication date.
    start = next((i for i, b in enumerate(xs) if b['d'] > event['publication_date']), None)
    if start is None:
        return 'NO_NEXT_SESSION_IN_CACHE', None
    if start + 34 >= len(xs):
        return 'RIGHT_EDGE_UNOBSERVED', None

    # Sweep must appear in sessions 1..15 after the first permitted session.
    for sweep_i in range(start, min(start + 15, len(xs) - 1)):
        confirmed_lows = [i for i in range(3, sweep_i - 3) if pivot_low(xs, i)]
        if not confirmed_lows:
            continue
        low_i = confirmed_lows[-1]
        if not (xs[sweep_i]['l'] < xs[low_i]['l'] and xs[sweep_i]['c'] > xs[low_i]['l']):
            continue

        # The lower-high anchor must be confirmed before the sweep and lower than prior confirmed high.
        confirmed_highs = [i for i in range(3, sweep_i - 3) if pivot_high(xs, i)]
        lower_high_i = next(
            (confirmed_highs[j] for j in range(len(confirmed_highs) - 1, 0, -1)
             if xs[confirmed_highs[j]]['h'] < xs[confirmed_highs[j - 1]]['h']),
            None,
        )
        if lower_high_i is None:
            continue

        # Break must occur 1..8 sessions after sweep.
        break_i = next(
            (i for i in range(sweep_i + 1, min(sweep_i + 9, len(xs)))
             if xs[i]['c'] > xs[lower_high_i]['h']),
            None,
        )
        if break_i is None:
            continue

        bears = [i for i in range(sweep_i, break_i + 1) if xs[i]['c'] < xs[i]['o']]
        if not bears:
            continue
        poi_i = bears[-1]
        zone_low, zone_high = xs[poi_i]['l'], xs[poi_i]['o']

        reclaim_i = next(
            (i for i in range(break_i + 1, min(break_i + 11, len(xs)))
             if xs[i]['l'] <= zone_high and xs[i]['h'] >= zone_low and xs[i]['c'] >= zone_high),
            None,
        )
        if reclaim_i is None:
            continue
        entry_i = reclaim_i + 1
        if entry_i >= len(xs):
            return 'ENTRY_UNOBSERVED', None
        return 'SEED', {
            **event,
            'eligible_date': xs[start]['d'],
            'sweep_date': xs[sweep_i]['d'],
            'sweep_anchor_date': xs[low_i]['d'],
            'choch_date': xs[break_i]['d'],
            'lh_anchor_date': xs[lower_high_i]['d'],
            'poi_date': xs[poi_i]['d'],
            'zone_low': round(zone_low, 6),
            'zone_high': round(zone_high, 6),
            'reclaim_date': xs[reclaim_i]['d'],
            'planned_entry_date': xs[entry_i]['d'],
        }
    return 'NO_COMPLETED_CHAIN_IN_WINDOW', None


def main() -> None:
    pre = json.loads(PRE.read_text())
    assert pre['decision'] == 'PREREGISTRATION_COMPLETE__OUTCOME_BLIND_SEED_GENERATION_AUTHORIZED'
    assert not any(pre[k] for k in ('production_write', 'frontend_write', 'watchlist_write'))
    OUT.mkdir(parents=True, exist_ok=False)
    events = load_events()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        grouped[e['symbol']].append(e)

    all_rows: list[dict] = []
    for number, (symbol, items) in enumerate(sorted(grouped.items()), 1):
        xs = load_bars(symbol)
        for event in items:
            status, seed = find_first_chain(event, xs)
            row = {**event, 'seed_status': status}
            if seed:
                row.update(seed)
            all_rows.append(row)
        if number % 500 == 0:
            print(json.dumps({'symbols': number, 'events': len(all_rows)}, ensure_ascii=False), flush=True)

    # One event gives at most one setup; same symbol/entry identity keeps earliest public event only.
    seeded = [r for r in all_rows if r['seed_status'] == 'SEED']
    chosen: dict[tuple[str, str], dict] = {}
    for r in sorted(seeded, key=lambda x: (x['symbol'], x['planned_entry_date'], x['publication_date'], x['announcement_id'])):
        chosen.setdefault((r['symbol'], r['planned_entry_date']), r)
    seeds = sorted(chosen.values(), key=lambda x: (x['planned_entry_date'], x['symbol'], x['announcement_id']))
    fields = sorted({k for row in all_rows for k in row} | {k for row in seeds for k in row})
    for name, rows in [('v565_all_events.csv', all_rows), ('v565_outcome_blind_seeds.csv', seeds)]:
        with (OUT / name).open('w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
            w.writeheader(); w.writerows(rows)

    years = ['2024', '2025']
    report = {
        'version': 'V565_PIT_COMMITMENT_SMC_RESPONSE_SEED_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input_contract': 'V564 frozen event taxonomy plus local daily_750 OHLCV only through planned entry; no outcome/trade/PnL/exit file is read.',
        'events_selected': len(events),
        'event_years': dict(Counter(r['event_year'] for r in events)),
        'status_counts': dict(Counter(r['seed_status'] for r in all_rows)),
        'raw_completed_chain_count': len(seeded),
        'canonical_seed_count': len(seeds),
        'canonical_seed_years': {y: sum(r['planned_entry_date'][:4] == y for r in seeds) for y in sorted({r['planned_entry_date'][:4] for r in seeds})},
        'complete_evaluation_seed_years': {y: sum(r['planned_entry_date'][:4] == y for r in seeds) for y in years},
        'invariants': {
            'no_outcome_or_trade_files_read': True,
            'all_entries_after_publication': all(r['planned_entry_date'] > r['publication_date'] for r in seeds),
            'all_sweep_anchors_confirmed_before_sweep': all(r['sweep_anchor_date'] < r['sweep_date'] for r in seeds),
            'all_lh_anchors_confirmed_before_sweep': all(r['lh_anchor_date'] < r['sweep_date'] for r in seeds),
            'all_causal_nodes_before_entry': all(r['sweep_date'] < r['choch_date'] < r['reclaim_date'] < r['planned_entry_date'] for r in seeds),
            'one_seed_per_symbol_entry_date': len(seeds) == len({(r['symbol'], r['planned_entry_date']) for r in seeds}),
        },
        'decision': 'OUTCOME_BLIND_SEED_COMPLETE__INDEPENDENT_ORACLE_REQUIRED_BEFORE_REPLAY',
        'artifacts': {'out_dir': str(OUT), 'all_events': str(OUT / 'v565_all_events.csv'), 'seeds': str(OUT / 'v565_outcome_blind_seeds.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v565_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
