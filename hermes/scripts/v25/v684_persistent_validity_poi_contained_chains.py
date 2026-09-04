#!/usr/bin/env python3
"""V684 no-write: V683 persistent-validity W->D->60m pure-SMC chains.

This is a new outcome-blind ontology.  It reads only same-source OHLCV and emits
state timestamps/zones plus causal terminal cancellations.  It never reads or
emits execution outcomes, indicators, targets, stops, or performance fields.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
DAILY = ROOT / 'intraday_cache/sina_raw_daily_v379'
M60 = ROOT / 'intraday_cache/sina_m60_v1'
V677 = AUD / 'v677_three_timeframe_semantic_source_audit_latest.json'
PREREG = AUD / 'v683_persistent_validity_poi_contained_takeover_preregistration_20260811.md'
OUT = AUD / f'v684_persistent_validity_poi_contained_chains_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v684_persistent_validity_poi_contained_chains_latest.json'

spec = importlib.util.spec_from_file_location('v677_core', ROOT / 'scripts/v25/v677_three_timeframe_semantic_source_audit.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def timekey(value: str) -> str:
    return ''.join(ch for ch in value if ch.isdigit())


def index(rows: list[dict]) -> dict[str, int]:
    return {x['t']: i for i, x in enumerate(rows)}


def typed(events: set[tuple], kind: str) -> list[tuple]:
    return sorted((x for x in events if x[1] == kind), key=lambda x: x[2])


def later(events: list[tuple], stamp: str, segment: int, rows: list[dict], pos: dict[str, int]) -> list[tuple]:
    return [x for x in events if x[2] > stamp and rows[pos[x[2]]]['segment'] == segment]


def intersects(bar: dict, low: float, high: float) -> bool:
    return bar['l'] <= high and bar['h'] >= low


def cancel(row: dict, code: str) -> dict:
    row['terminal'] = code
    return row


def permissions(weekly: list[dict], events: set[tuple]) -> list[dict]:
    pos, lows = index(weekly), typed(events, 'PIVOT_L')
    swept = {x[2] for x in typed(events, 'SSL_SWEEP_RECLAIM')}
    out = []
    for br in typed(events, 'BULL_BREAK'):
        i = pos[br[2]]
        prior = [x for x in lows if pos[x[2]] < i and x[3] <= br[2]]
        if prior:
            low = max(prior, key=lambda x: pos[x[2]])
            out.append({'time': br[2], 'protected_low': low[4], 'segment': weekly[i]['segment'],
                        'origin': 'sweep_reversal' if any(x < br[2] for x in swept) else 'protected_low'})
    return out


def active_w1(perms: list[dict], daily_time: str, segment: int) -> dict | None:
    # V677 primitives reset at source-segment boundaries; permission cannot bridge one.
    candidates = [p for p in perms if p['time'] < daily_time and p['segment'] == segment]
    return max(candidates, key=lambda x: x['time']) if candidates else None


def weekly_invalidated(weekly: list[dict], w1: dict, until_time: str) -> bool:
    # Only weekly closes that have completed by the time being evaluated exist here.
    return any(x['t'] > w1['time'] and x['t'] <= until_time and x['c'] < w1['protected_low']
               for x in weekly if x['segment'] == w1['segment'])


def symbol_chains(symbol: str, daily: list[dict], h60: list[dict]) -> list[dict]:
    weekly = core.weekly_rows(daily)
    de, he, we = core.primitives_a(daily, 'D'), core.primitives_a(h60, 'M60'), core.primitives_a(weekly, 'W')
    di, hi = index(daily), index(h60)
    dssl, dbull, dob = typed(de, 'SSL_SWEEP_RECLAIM'), typed(de, 'BULL_BREAK'), typed(de, 'BULL_EVENT_OB')
    hssl, hbull, hob = typed(he, 'SSL_SWEEP_RECLAIM'), typed(he, 'BULL_BREAK'), typed(he, 'BULL_EVENT_OB')
    perms, seen, result = permissions(weekly, we), set(), []
    for d1 in dssl:
        d1i, seg = di[d1[2]], daily[di[d1[2]]]['segment']
        row = {'symbol': symbol, 'daily_ssl_time': d1[2], 'daily_ssl_pivot_time': d1[3],
               'daily_ssl_price': d1[4], 'terminal': ''}
        w1 = active_w1(perms, d1[2], seg)
        if not w1:
            result.append(cancel(row, 'NO_W1_PERMISSION')); continue
        row.update(weekly_permission_time=w1['time'], weekly_permission_origin=w1['origin'],
                   weekly_protected_low=w1['protected_low'])
        d2 = None
        for event in later(dbull, d1[2], seg, daily, di):
            if weekly_invalidated(weekly, w1, event[2]):
                result.append(cancel(row, 'W1_INVALIDATED')); break
            if any(daily[j]['c'] < d1[4] for j in range(d1i + 1, di[event[2]] + 1)):
                result.append(cancel(row, 'D1_LOW_INVALIDATED')); break
            d2 = event; break
        if row['terminal']:
            continue
        if not d2:
            result.append(cancel(row, 'NO_D2_BREAK')); continue
        ob = next((x for x in dob if x[2] == d2[2]), None)
        if not ob:
            result.append(cancel(row, 'NO_D3_BEARISH_OB')); continue
        low, high = ob[4], ob[5]
        key = (symbol, d2[2], ob[3], low, high)
        if key in seen:
            continue
        seen.add(key)
        row.update(daily_break_time=d2[2], daily_break_pivot_time=d2[3], daily_ob_time=ob[3],
                   daily_zone_low=low, daily_zone_high=high)
        d4i = None
        for j in range(di[d2[2]] + 1, len(daily)):
            bar = daily[j]
            if bar['segment'] != seg:
                break
            if weekly_invalidated(weekly, w1, bar['t']):
                result.append(cancel(row, 'W1_INVALIDATED')); break
            if bar['c'] < low:
                result.append(cancel(row, 'D_POI_INVALIDATED')); break
            if intersects(bar, low, high):
                d4i = j; break
        if row['terminal']:
            continue
        if d4i is None:
            result.append(cancel(row, 'NO_D4_FIRST_TOUCH')); continue
        d4 = daily[d4i]
        row['daily_first_touch_time'] = d4['t']
        h1i = None
        for j, bar in enumerate(h60):
            day = timekey(bar['t'])[:8]
            if day <= d4['t']:
                continue
            if weekly_invalidated(weekly, w1, day):
                result.append(cancel(row, 'W1_INVALIDATED')); break
            if bar['c'] < low:
                result.append(cancel(row, 'H_CLOSE_INVALIDATES_D_POI')); break
            if intersects(bar, low, high):
                h1i = j; break
        if row['terminal']:
            continue
        if h1i is None:
            result.append(cancel(row, 'END_OF_SOURCE')); continue
        row['h60_first_touch_time'] = h60[h1i]['t']
        hseg, h2, was_outside = h60[h1i]['segment'], None, False
        for event in later(hssl, h60[h1i]['t'], hseg, h60, hi):
            ei = hi[event[2]]
            invalid = None
            for j in range(h1i + 1, ei + 1):
                bar, day = h60[j], timekey(h60[j]['t'])[:8]
                if weekly_invalidated(weekly, w1, day):
                    invalid = 'W1_INVALIDATED'; break
                if bar['c'] < low:
                    invalid = 'H_CLOSE_INVALIDATES_D_POI'; break
                if not intersects(bar, low, high):
                    was_outside = True
                elif was_outside:
                    invalid = 'REPEATED_D_POI_TOUCH_BEFORE_H2'; break
            if invalid:
                result.append(cancel(row, invalid)); break
            h2 = event; break
        if row['terminal']:
            continue
        if not h2:
            result.append(cancel(row, 'NO_H2_LOCAL_SSL_RECLAIM')); continue
        row.update(h60_ssl_time=h2[2], h60_ssl_pivot_time=h2[3], h60_ssl_price=h2[4])
        h3 = None
        for event in later(hbull, h2[2], hseg, h60, hi):
            ei = hi[event[2]]
            invalid = next(('W1_INVALIDATED' if weekly_invalidated(weekly, w1, timekey(h60[j]['t'])[:8])
                            else 'H_CLOSE_INVALIDATES_D_POI' if h60[j]['c'] < low else '')
                           for j in range(hi[h2[2]] + 1, ei + 1))
            if invalid:
                result.append(cancel(row, invalid)); break
            h3 = event; break
        if row['terminal']:
            continue
        if not h3:
            result.append(cancel(row, 'NO_H3_LOCAL_BULL_BREAK')); continue
        hob_event = next((x for x in hob if x[2] == h3[2]), None)
        if not hob_event:
            result.append(cancel(row, 'NO_H4_LOCAL_OB')); continue
        hlow, hhigh = hob_event[4], hob_event[5]
        if max(low, hlow) > min(high, hhigh):
            result.append(cancel(row, 'LOCAL_OB_OUTSIDE_D_POI')); continue
        row.update(h60_break_time=h3[2], h60_break_pivot_time=h3[3], h60_ob_time=hob_event[3],
                   h60_ob_low=hlow, h60_ob_high=hhigh)
        reclaim = None
        for j in range(hi[h3[2]] + 1, len(h60)):
            bar, day = h60[j], timekey(h60[j]['t'])[:8]
            if bar['segment'] != hseg:
                break
            if weekly_invalidated(weekly, w1, day):
                result.append(cancel(row, 'W1_INVALIDATED')); break
            if bar['c'] < low:
                result.append(cancel(row, 'H_CLOSE_INVALIDATES_D_POI')); break
            if intersects(bar, hlow, hhigh):
                if bar['c'] > hhigh and j + 1 < len(h60):
                    nxt = h60[j + 1]
                    if nxt['segment'] == hseg and nxt['l'] >= hlow and nxt['c'] >= hhigh:
                        reclaim = j
                break
        if row['terminal']:
            continue
        if reclaim is None:
            result.append(cancel(row, 'H4_RECLAIM_OR_HOLD_FAILED')); continue
        if reclaim + 2 >= len(h60):
            result.append(cancel(row, 'END_OF_SOURCE')); continue
        entry = h60[reclaim + 2]
        day = timekey(entry['t'])[:8]
        if weekly_invalidated(weekly, w1, day):
            result.append(cancel(row, 'W1_INVALIDATED')); continue
        if entry['o'] <= max(h2[4], low):
            result.append(cancel(row, 'OPEN_AT_OR_BELOW_STRUCTURE_STOP_CANCEL')); continue
        row.update(h60_reclaim_time=h60[reclaim]['t'], h60_hold_time=h60[reclaim + 1]['t'],
                   next_h60_open_time=entry['t'], terminal='SEED_READY')
        result.append(row)
    return result


def main() -> None:
    source = json.loads(V677.read_text())
    if source.get('decision') != 'V677_SOURCE_AND_SEMANTIC_AUDIT_PASS__OUTCOME_BLIND_STATE_MACHINE_SEEDS_ALLOWED':
        raise SystemExit('V677 source gate failed')
    OUT.mkdir(parents=True, exist_ok=False)
    rows, errors = [], []
    files = sorted(DAILY.glob('*_raw_daily.json.gz'))
    for n, path in enumerate(files, 1):
        symbol = core.symbol_from_path(path)
        try:
            daily = core.daily_rows(path)
            code, exchange = symbol.split('.')
            h60, bad = core.m60_rows(M60 / f'{code}_{exchange}_m60_sina.json.gz', {x['t']: x['segment'] for x in daily})
            if bad:
                raise ValueError(f'unexpected_m60_bad_days:{len(bad)}')
            rows.extend(symbol_chains(symbol, daily, h60))
        except Exception as exc:
            errors.append({'symbol': symbol, 'reason': f'{type(exc).__name__}:{exc}'})
        if n % 250 == 0:
            print(f'V684 progress {n}: terminals={len(rows)} errors={len(errors)}', flush=True)
    fields = sorted({k for x in rows for k in x})
    artifact = OUT / 'v684_terminal_chain_rows.csv'
    with artifact.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    ready = [x for x in rows if x['terminal'] == 'SEED_READY']
    chronology = all(timekey(x['weekly_permission_time']) < timekey(x['daily_ssl_time']) < timekey(x['daily_break_time']) < timekey(x['daily_first_touch_time']) < timekey(x['h60_first_touch_time']) < timekey(x['h60_ssl_time']) < timekey(x['h60_break_time']) < timekey(x['h60_hold_time']) < timekey(x['next_h60_open_time']) for x in ready)
    report = {'version': 'V684_PERSISTENT_VALIDITY_POI_CONTAINED_CHAINS_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'preregistration': str(PREREG), 'source_gate': source['decision'], 'input_symbols': len(files), 'terminal_counts': dict(Counter(x['terminal'] for x in rows)), 'ready_chain_count': len(ready), 'unique_ready_identity_count': len({(x['symbol'], x['weekly_permission_time'], x['daily_ssl_time'], x['daily_break_time'], x['daily_ob_time'], x['daily_first_touch_time'], x['h60_ssl_time'], x['h60_break_time'], x['h60_ob_time'], x['h60_hold_time']) for x in ready}), 'chronology_pass': chronology, 'symbol_errors': len(errors), 'error_samples': errors[:100], 'decision': 'V684_OUTCOME_BLIND_PERSISTENT_CHAINS_READY__INDEPENDENT_ORACLE_REQUIRED' if not errors and chronology else 'V684_CHAIN_CONTRACT_FAIL__STOP_BEFORE_ORACLE', 'artifact': str(artifact)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v684_report.json').write_text(text, encoding='utf-8'); LATEST.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
