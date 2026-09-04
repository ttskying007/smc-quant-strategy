#!/usr/bin/env python3
"""V424 independent no-outcome semantic and chronology audit for V423 R4."""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
SOURCE = AUD / 'v423_range_accumulation_breaker_latest.json'
OUT = AUD / f'v424_range_accumulation_breaker_integrity_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v424_range_accumulation_breaker_integrity_latest.json'
spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(b): return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]


def load(sym):
    try:
        raw = json.loads((KDIR / f"{sym.replace('.', '_')}_daily_750.json").read_text())
    except Exception:
        return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))], key=day)


def lifecycle(ks, start, low, high):
    touch = reclaim = None
    for i in range(start + 1, min(len(ks), start + 31)):
        b = ks[i]
        if f(b['c']) < low: return 'CANCEL_ZONE_INVALIDATED', touch, reclaim, i
        if touch is None:
            if f(b['l']) <= high: touch = i
        elif reclaim is None:
            if f(b['c']) > high: reclaim = i
        elif f(b['c']) > high and f(b['l']) >= low:
            return 'TAKEOVER_CONFIRMED', touch, reclaim, i
    observed = start + 30 < len(ks)
    if touch is None: return ('EXPIRE_NO_TOUCH_30B' if observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None: return ('EXPIRE_NO_RECLAIM_30B' if observed else 'WAIT_RECLAIM_UNOBSERVED'), touch, None, None
    return ('EXPIRE_NO_HOLD_30B' if observed else 'WAIT_HOLD_UNOBSERVED'), touch, reclaim, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SOURCE.read_text())
    with Path(report['artifacts']['rows']).open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    forbidden = [c for c in rows[0] if c != 'outcome_fields_present' and any(x in c.lower() for x in ('entry', 'exit', 'pnl', 'profit', 'win', 'loss', 'mae', 'mfe', 'tp', 'sl'))]
    duplicates = Counter((r['symbol'], r['event_idx'], r['poi_idx']) for r in rows)
    execution_duplicates = Counter((r['symbol'], r['takeover_idx']) for r in rows if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED')
    failures, checked, cache = Counter(), 0, {}
    for r in rows:
        sym = r['symbol']
        if sym not in cache: cache[sym] = load(sym)
        ks = cache[sym]
        if not ks:
            failures['MISSING_KLINE'] += 1; continue
        try:
            la, lb, ha, hb, ready, sweep, event, poi = [int(r[x]) for x in (
                'range_low_a_idx', 'range_low_b_idx', 'range_high_a_idx', 'range_high_b_idx',
                'range_ready_idx', 'sweep_idx', 'event_idx', 'poi_idx')]
        except (TypeError, ValueError):
            failures['NON_INTEGER_INDEX'] += 1; continue
        if not (max(la, lb, ha, hb) < ready < sweep <= poi < event == int(r['strict_lifecycle_start_idx'])):
            failures['ORDERING'] += 1; continue
        if event >= len(ks) or poi >= len(ks):
            failures['INDEX_OUT_OF_RANGE'] += 1; continue
        swings = v27.confirmed_swings(ks)
        lows = {x['idx']: x for x in swings['lows']}; highs = {x['idx']: x for x in swings['highs']}
        if not all(x in lows for x in (la, lb)) or not all(x in highs for x in (ha, hb)):
            failures['PIVOT_NOT_CONFIRMED'] += 1; continue
        if ready != max(lows[la]['confirm_idx'], lows[lb]['confirm_idx'], highs[ha]['confirm_idx'], highs[hb]['confirm_idx']):
            failures['READY_NOT_PIVOT_CONFIRMATION'] += 1; continue
        floor, ceiling = f(r['range_floor']), f(r['range_ceiling'])
        if abs(floor - max(f(lows[la]['price']), f(lows[lb]['price']))) > 1e-6 or abs(ceiling - min(f(highs[ha]['price']), f(highs[hb]['price']))) > 1e-6:
            failures['RANGE_PRICE_MISMATCH'] += 1; continue
        if not (f(ks[sweep]['l']) < floor * .997 and f(ks[sweep]['c']) > floor * 1.001):
            failures['SSL_NOT_REDERIVED'] += 1; continue
        if not f(ks[event]['c']) > ceiling * 1.002:
            failures['RANGE_BOS_NOT_REDERIVED'] += 1; continue
        low, high = f(r['zone_low']), f(r['zone_high'])
        b = ks[poi]
        if not (f(b['c']) < f(b['o']) and abs(low - f(b['l'])) < 1e-6 and abs(high - f(b['h'])) < 1e-6):
            failures['BREAKER_GEOMETRY_MISMATCH'] += 1; continue
        if any(f(x['c']) < low or f(x['l']) <= high for x in ks[poi + 1:event]):
            failures['BREAKER_NOT_FRESH'] += 1; continue
        state, touch, reclaim, takeover = lifecycle(ks, event, low, high)
        recorded = (r['lifecycle_state'], r['touch_idx'], r['reclaim_idx'], r['takeover_idx'])
        rebuilt = (state, '' if touch is None else str(touch), '' if reclaim is None else str(reclaim), '' if takeover is None else str(takeover))
        if recorded != rebuilt:
            failures['LIFECYCLE_MISMATCH'] += 1; continue
        checked += 1
    result = {
        'version': 'V424_RANGE_ACCUMULATION_BREAKER_INTEGRITY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'Independent raw-bar rederivation of V423 semantics and chronology; no marks, entries, exits, PnL, or promotion.',
        'criteria': {
            'confirmed_balance_pivots': True, 'all_prerequisites_visible_before_ssl': True,
            'ssl_and_range_bos_rederived': True, 'fresh_breaker_rederived': True,
            'lifecycle_rederived': True, 'one_row_per_symbol_event_poi': True, 'one_takeover_per_symbol_day': True,
            'no_outcome_fields': True,
        },
        'input_rows': len(rows), 'raw_rederived_rows': checked,
        'forbidden_input_fields': forbidden,
        'duplicate_extra_rows': sum(n - 1 for n in duplicates.values() if n > 1),
        'duplicate_execution_rows': sum(n - 1 for n in execution_duplicates.values() if n > 1),
        'failures': dict(failures),
        'pass': checked == len(rows) and not forbidden and not failures and all(n == 1 for n in duplicates.values()) and all(n == 1 for n in execution_duplicates.values()),
        'decision': 'INTEGRITY_PASS__R4_ELIGIBLE_FOR_ONE_FROZEN_T1_MARK_REPLAY' if checked == len(rows) and not forbidden and not failures and all(n == 1 for n in duplicates.values()) and all(n == 1 for n in execution_duplicates.values()) else 'INTEGRITY_FAIL__NO_REPLAY_ALLOWED',
        'artifacts': {'out_dir': str(OUT), 'latest': str(LATEST)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v424_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__': main()
