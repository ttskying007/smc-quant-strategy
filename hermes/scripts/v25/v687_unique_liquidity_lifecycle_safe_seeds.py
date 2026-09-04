#!/usr/bin/env python3
"""V687 no-write, outcome-blind unique-liquidity lifecycle-safe W->D->60m seeds.

The only allowed result is a causal chain identity plus state timestamps/zones or
one terminal cancellation reason per daily SSL seed.  No execution-price field
is read for E; no post-E OHLCV is inspected.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
DAILY = ROOT / 'intraday_cache/sina_raw_daily_v379'
M60 = ROOT / 'intraday_cache/sina_m60_v1'
V677 = AUDIT / 'v677_three_timeframe_semantic_source_audit_latest.json'
OUT = AUDIT / f'v687_unique_liquidity_lifecycle_safe_seeds_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v687_unique_liquidity_lifecycle_safe_seeds_latest.json'

spec = importlib.util.spec_from_file_location('v677_core', ROOT / 'scripts/v25/v677_three_timeframe_semantic_source_audit.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def by_type(events: set[tuple], name: str) -> list[tuple]:
    return sorted((x for x in events if x[1] == name), key=lambda x: x[2])


def index_by_time(rows: list[dict]) -> dict[str, int]:
    return {row['t']: i for i, row in enumerate(rows)}


def timekey(value: str) -> str:
    """Canonical chronological key across D=YYYYMMDD and H=YYYY-MM-DD HH:MM:SS."""
    return ''.join(ch for ch in value if ch.isdigit())


def after(events: list[tuple], timestamp: str, segment: int, index: dict[str, int], rows: list[dict]) -> list[tuple]:
    return [x for x in events if x[2] > timestamp and rows[index[x[2]]]['segment'] == segment]


def timekey(value: str) -> str:
    """Canonical order across daily YYYYMMDD and 60m ISO timestamps."""
    return ''.join(ch for ch in value if ch.isdigit())


def weekly_permissions(weekly: list[dict], events: set[tuple]) -> list[dict]:
    idx = index_by_time(weekly)
    lows = by_type(events, 'PIVOT_L')
    sweeps = {x[2] for x in by_type(events, 'SSL_SWEEP_RECLAIM')}
    out = []
    for br in by_type(events, 'BULL_BREAK'):
        i = idx[br[2]]
        low_candidates = [x for x in lows if x[3] <= br[2] and idx[x[2]] < i]
        if not low_candidates:
            continue
        low = max(low_candidates, key=lambda x: idx[x[2]])
        protected = low[4]
        invalid = next((weekly[j]['t'] for j in range(i + 1, len(weekly)) if weekly[j]['segment'] == weekly[i]['segment'] and weekly[j]['c'] < protected), '')
        prior_sweep = any(x < br[2] for x in sweeps)
        out.append({'time': br[2], 'protected_low': protected, 'invalid': invalid, 'segment': weekly[i]['segment'], 'origin': 'sweep_reversal' if prior_sweep else 'protected_low'})
    return out


def selected_w1(perms: list[dict], daily_date: str) -> dict | None:
    active = [p for p in perms if p['time'] < daily_date and (not p['invalid'] or daily_date <= p['invalid'])]
    return max(active, key=lambda x: x['time']) if active else None


def cancel(row: dict, code: str) -> dict:
    row['terminal'] = code
    return row


def lifecycle_cancel_code(daily: list[dict], h60: list[dict], weekly: list[dict], *, w1: dict, d1_time: str, d1_low: float, d2_time: str, d4_time: str, zone_low: float, h1_time: str, entry_time: str) -> str:
    """Hard cancellations maintained to the next executable open, no outcomes."""
    entry_day = timekey(entry_time)[:8]
    # Completed weekly bar only: the current intraday week's close is not known.
    if any(bar['c'] < w1['protected_low'] for bar in weekly if w1['time'] < bar['t'] < entry_day):
        return 'W1_PROTECTED_LOW_INVALIDATED'
    if any(bar['c'] < d1_low for bar in daily if d2_time < bar['t'] < entry_day):
        return 'D1_LOW_REBREAK_AFTER_D2'
    if any(bar['c'] < zone_low for bar in daily if d4_time < bar['t'] < entry_day):
        return 'DAILY_POI_CLOSE_INVALIDATED_AFTER_D4'
    if any(bar['c'] < zone_low for bar in h60 if h1_time < bar['t'] < entry_time):
        return 'H60_POI_CLOSE_INVALIDATED_AFTER_H1'
    return ''


def canonical_ssl_events(events: list[tuple]) -> list[tuple]:
    """One chain reference per sweep bar: most recently formed raided pool."""
    chosen: dict[str, tuple] = {}
    for event in events:
        old = chosen.get(event[2])
        if old is None or (event[3], event[4]) > (old[3], old[4]):
            chosen[event[2]] = event
    return sorted(chosen.values(), key=lambda x: (x[2], x[3], x[4]))


def symbol_chains(symbol: str, daily: list[dict], h60: list[dict]) -> list[dict]:
    weekly = core.weekly_rows(daily)
    de, he, we = core.primitives_a(daily, 'D'), core.primitives_a(h60, 'M60'), core.primitives_a(weekly, 'W')
    di, hi = index_by_time(daily), index_by_time(h60)
    dssl, dbull, dob = canonical_ssl_events(by_type(de, 'SSL_SWEEP_RECLAIM')), by_type(de, 'BULL_BREAK'), by_type(de, 'BULL_EVENT_OB')
    hssl, hbull, hob = canonical_ssl_events(by_type(he, 'SSL_SWEEP_RECLAIM')), by_type(he, 'BULL_BREAK'), by_type(he, 'BULL_EVENT_OB')
    permissions = weekly_permissions(weekly, we)
    results: list[dict] = []
    seen_poi = set()
    for d1 in dssl:
        d1_i = di[d1[2]]; seg = daily[d1_i]['segment']
        row = {'symbol': symbol, 'daily_ssl_time': d1[2], 'daily_ssl_pivot_time': d1[3], 'daily_ssl_price': d1[4], 'terminal': ''}
        w1 = selected_w1(permissions, d1[2])
        if not w1:
            results.append(cancel(row, 'NO_W1_PERMISSION')); continue
        row.update({'weekly_permission_time': w1['time'], 'weekly_permission_origin': w1['origin'], 'weekly_protected_low': w1['protected_low']})
        # D2 must happen before the D1 raid-low is closed below.
        d2 = None
        for event in after(dbull, d1[2], seg, di, daily):
            until = di[event[2]]
            if any(daily[j]['c'] < d1[4] for j in range(d1_i + 1, until + 1)):
                break
            d2 = event; break
        if not d2:
            reason = 'D1_LOW_INVALIDATED' if any(x['c'] < d1[4] for x in daily[d1_i + 1:] if x['segment'] == seg) else 'NO_D2_BREAK'
            results.append(cancel(row, reason)); continue
        d2_i = di[d2[2]]
        ob = next((x for x in dob if x[2] == d2[2]), None)
        if not ob:
            results.append(cancel(row, 'NO_D3_BEARISH_OB')); continue
        zl, zh = ob[4], ob[5]
        poi_key = (symbol, d2[2], ob[3], zl, zh)
        if poi_key in seen_poi:
            continue
        seen_poi.add(poi_key)
        row.update({'daily_break_time': d2[2], 'daily_break_pivot_time': d2[3], 'daily_ob_time': ob[3], 'daily_zone_low': zl, 'daily_zone_high': zh})
        d4_i = None
        for j in range(d2_i + 1, len(daily)):
            bar = daily[j]
            if bar['segment'] != seg:
                break
            if bar['c'] < zl:
                break
            if bar['l'] <= zh and bar['h'] >= zl:
                d4_i = j; break
        if d4_i is None:
            invalid = any(x['c'] < zl for x in daily[d2_i + 1:] if x['segment'] == seg)
            results.append(cancel(row, 'DAILY_POI_CLOSE_INVALIDATED' if invalid else 'NO_D4_FIRST_TOUCH')); continue
        d4 = daily[d4_i]; row['daily_first_touch_time'] = d4['t']
        # Daily D4 is known only at its close: H1 begins strictly on a later date.
        h1_i = None
        hseg = None
        for j, bar in enumerate(h60):
            date = bar['t'][:10].replace('-', '')
            if date <= d4['t']:
                continue
            if bar['c'] < zl:
                break
            if bar['l'] <= zh and bar['h'] >= zl:
                h1_i, hseg = j, bar['segment']; break
        if h1_i is None:
            invalid = any(x['c'] < zl for x in h60 if x['t'][:10].replace('-', '') > d4['t'])
            results.append(cancel(row, 'H1_ZONE_CLOSE_INVALIDATED' if invalid else 'END_OF_SOURCE')); continue
        row['h60_first_touch_time'] = h60[h1_i]['t']
        h2 = None
        repeat = False
        for event in after(hssl, h60[h1_i]['t'], hseg, hi, h60):
            candidate_i = hi[event[2]]
            if any(h60[j]['l'] <= zh and h60[j]['h'] >= zl for j in range(h1_i + 1, candidate_i)):
                repeat = True; break
            h2 = event; break
        if not h2:
            results.append(cancel(row, 'H2_REPEAT_TOUCH' if repeat else 'NO_H2_LOCAL_SSL_RECLAIM')); continue
        h2_i = hi[h2[2]]; row.update({'h60_ssl_time': h2[2], 'h60_ssl_pivot_time': h2[3], 'h60_ssl_price': h2[4]})
        h3 = next(iter(after(hbull, h2[2], hseg, hi, h60)), None)
        if not h3:
            results.append(cancel(row, 'NO_H3_LOCAL_BULL_BREAK')); continue
        local = next((x for x in hob if x[2] == h3[2]), None)
        if not local:
            results.append(cancel(row, 'NO_H4_LOCAL_OB')); continue
        local_low, local_high = local[4], local[5]
        row.update({'h60_break_time': h3[2], 'h60_break_pivot_time': h3[3], 'h60_ob_time': local[3], 'h60_ob_low': local_low, 'h60_ob_high': local_high})
        h3_i = hi[h3[2]]; reclaim_i = None
        for j in range(h3_i + 1, len(h60)):
            bar = h60[j]
            if bar['segment'] != hseg:
                break
            if bar['l'] <= local_high and bar['h'] >= local_low:
                if bar['c'] > local_high and j + 1 < len(h60):
                    nxt = h60[j + 1]
                    if nxt['segment'] == hseg and nxt['l'] >= local_low and nxt['c'] >= local_high:
                        reclaim_i = j
                break
        if reclaim_i is None:
            results.append(cancel(row, 'H4_RECLAIM_OR_HOLD_FAILED')); continue
        if reclaim_i + 2 >= len(h60):
            results.append(cancel(row, 'END_OF_SOURCE')); continue
        entry_time = h60[reclaim_i + 2]['t']
        lifecycle_cancel = lifecycle_cancel_code(
            daily, h60, weekly, w1=w1, d1_time=d1[2], d1_low=d1[4],
            d2_time=d2[2], d4_time=d4['t'], zone_low=zl,
            h1_time=h60[h1_i]['t'], entry_time=entry_time,
        )
        if lifecycle_cancel:
            results.append(cancel(row, lifecycle_cancel)); continue
        row.update({'h60_reclaim_time': h60[reclaim_i]['t'], 'h60_hold_time': h60[reclaim_i + 1]['t'], 'next_h60_open_time': entry_time, 'terminal': 'SEED_READY'})
        results.append(row)
    return results


def main() -> None:
    source = json.loads(V677.read_text())
    if source.get('decision') != 'V677_SOURCE_AND_SEMANTIC_AUDIT_PASS__OUTCOME_BLIND_STATE_MACHINE_SEEDS_ALLOWED':
        raise SystemExit('V677 did not authorize V687')
    OUT.mkdir(parents=True, exist_ok=False)
    all_rows, errors = [], []
    for n, path in enumerate(sorted(DAILY.glob('*_raw_daily.json.gz')), 1):
        symbol = core.symbol_from_path(path)
        try:
            daily = core.daily_rows(path); code, exchange = symbol.split('.')
            h60, bad = core.m60_rows(M60 / f'{code}_{exchange}_m60_sina.json.gz', {x['t']: x['segment'] for x in daily})
            if bad:
                raise ValueError(f'unexpected_m60_bad_days:{len(bad)}')
            all_rows.extend(symbol_chains(symbol, daily, h60))
        except Exception as exc:
            errors.append({'symbol': symbol, 'reason': f'{type(exc).__name__}:{exc}'})
        if n % 250 == 0:
            print(f'V687 progress {n}: terminal_rows={len(all_rows)} errors={len(errors)}', flush=True)
    fields = sorted({k for row in all_rows for k in row})
    csv_path = OUT / 'v687_terminal_chain_rows.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(all_rows)
    terminal = Counter(x['terminal'] for x in all_rows)
    ready = [x for x in all_rows if x['terminal'] == 'SEED_READY']
    identities = {(x['symbol'], x['weekly_permission_time'], x['daily_ssl_time'], x['daily_break_time'], x['daily_ob_time'], x['daily_first_touch_time'], x['h60_ssl_time'], x['h60_break_time'], x['h60_ob_time'], x['h60_hold_time']) for x in ready}
    chronology = all(
        timekey(x['weekly_permission_time']) < timekey(x['daily_ssl_time']) < timekey(x['daily_break_time']) < timekey(x['daily_first_touch_time'])
        and timekey(x['daily_first_touch_time']) < timekey(x['h60_first_touch_time']) < timekey(x['h60_ssl_time']) < timekey(x['h60_break_time']) < timekey(x['h60_reclaim_time']) < timekey(x['h60_hold_time']) < timekey(x['next_h60_open_time'])
        for x in ready
    )
    decision = 'V687_UNIQUE_LIQUIDITY_CHAIN_SEEDS_READY__INDEPENDENT_ORACLE_REQUIRED' if not errors and len(identities) == len(ready) and chronology else 'V687_SEED_CONTRACT_FAIL__STOP_BEFORE_ORACLE'
    report = {'version': 'V687_UNIQUE_LIQUIDITY_LIFECYCLE_SAFE_SEEDS_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False, 'source_gate': source.get('decision'), 'input_symbols': len(list(DAILY.glob('*_raw_daily.json.gz'))), 'terminal_counts': dict(terminal), 'ready_chain_count': len(ready), 'unique_ready_identity_count': len(identities), 'chronology_pass': chronology, 'symbol_errors': len(errors), 'error_samples': errors[:100], 'decision': decision, 'artifact': str(csv_path)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v687_report.json').write_text(text, encoding='utf-8'); LATEST.write_text(text, encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
