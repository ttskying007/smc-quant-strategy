#!/usr/bin/env python3
"""V423 no-outcome R4 generator: range accumulation -> SSL -> range reclaim -> bull break -> breaker retest.

This is deliberately distinct from R1/R2/R3:
- it requires a confirmed two-sided balance range before the sweep;
- the structure event is a break of that pre-existing range high, not an arbitrary CHOCH;
- it produces only causal lifecycle evidence, never entries or outcomes.
"""
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
OUT = AUD / f'v423_range_accumulation_breaker_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v423_range_accumulation_breaker_latest.json'
spec = importlib.util.spec_from_file_location('v27', ROOT / 'scripts/v25/smc_core_v27.py')
v27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v27)


def f(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(b):
    return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]


def load(path):
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    return sorted(
        [b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))],
        key=day,
    )


def symbol(path):
    code, exchange = path.name.replace('_daily_750.json', '').split('_')
    return f'{code}.{exchange}'


def lifecycle(ks, start, low, high):
    """First post-breaker retest -> reclaim -> next hold; close below zone invalidates."""
    touch = reclaim = None
    for i in range(start + 1, min(len(ks), start + 31)):
        b = ks[i]
        if f(b['c']) < low:
            return 'CANCEL_ZONE_INVALIDATED', touch, reclaim, i
        if touch is None:
            if f(b['l']) <= high:
                touch = i
        elif reclaim is None:
            if f(b['c']) > high:
                reclaim = i
        elif f(b['c']) > high and f(b['l']) >= low:
            return 'TAKEOVER_CONFIRMED', touch, reclaim, i
    observed = start + 30 < len(ks)
    if touch is None:
        return ('EXPIRE_NO_TOUCH_30B' if observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None:
        return ('EXPIRE_NO_RECLAIM_30B' if observed else 'WAIT_RECLAIM_UNOBSERVED'), touch, None, None
    return ('EXPIRE_NO_HOLD_30B' if observed else 'WAIT_HOLD_UNOBSERVED'), touch, reclaim, None


def range_candidates(swings, ks):
    """Two confirmed highs and lows form a prior balance; no outcome-dependent selection."""
    out = []
    highs, lows = swings['highs'], swings['lows']
    for lo_a_i in range(len(lows) - 1):
        lo_a = lows[lo_a_i]
        for lo_b in lows[lo_a_i + 1:]:
            if not (8 <= lo_b['idx'] - lo_a['idx'] <= 60):
                continue
            floor = max(f(lo_a['price']), f(lo_b['price']))
            if abs(f(lo_a['price']) / f(lo_b['price']) - 1) > 0.015:
                continue
            hs = [h for h in highs if lo_a['confirm_idx'] < h['idx'] < lo_b['idx']]
            if len(hs) < 2:
                continue
            hs = sorted(hs, key=lambda h: h['idx'])[-2:]
            ceiling = min(f(hs[0]['price']), f(hs[1]['price']))
            if ceiling <= floor or ceiling / floor - 1 > 0.20:
                continue
            ready = max(lo_a['confirm_idx'], lo_b['confirm_idx'], hs[0]['confirm_idx'], hs[1]['confirm_idx'])
            if ready >= len(ks):
                continue
            out.append({'low_a': lo_a, 'low_b': lo_b, 'high_a': hs[0], 'high_b': hs[1],
                        'floor': floor, 'ceiling': ceiling, 'ready_idx': ready})
    return out


def fresh_bearish_breaker(ks, sweep_i, break_i):
    """Last bearish breaker at/after SSL and before range-high break, unmitigated pre-break."""
    for i in range(break_i - 1, sweep_i - 1, -1):
        if f(ks[i]['c']) < f(ks[i]['o']):
            low, high = f(ks[i]['l']), f(ks[i]['h'])
            if not any(f(b['c']) < low or f(b['l']) <= high for b in ks[i + 1:break_i]):
                return i, low, high
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, counts = [], Counter()
    for path in sorted(KDIR.glob('*_daily_750.json')):
        ks = load(path)
        if len(ks) < 100:
            continue
        counts['symbols_scanned'] += 1
        swings = v27.confirmed_swings(ks)
        for rg in range_candidates(swings, ks):
            start = rg['ready_idx'] + 1
            sweep_i = None
            for i in range(start, min(len(ks), start + 61)):
                if f(ks[i]['l']) < rg['floor'] * 0.997 and f(ks[i]['c']) > rg['floor'] * 1.001:
                    sweep_i = i
                    break
            if sweep_i is None:
                counts['NO_SSL_AFTER_BALANCE'] += 1
                continue
            break_i = None
            for i in range(sweep_i + 1, min(len(ks), sweep_i + 31)):
                if f(ks[i]['c']) > rg['ceiling'] * 1.002:
                    break_i = i
                    break
            if break_i is None:
                counts['NO_RANGE_HIGH_BREAK_AFTER_SSL'] += 1
                continue
            breaker = fresh_bearish_breaker(ks, sweep_i, break_i)
            if breaker is None:
                counts['NO_FRESH_POST_SSL_BREAKER'] += 1
                continue
            poi_i, low, high = breaker
            state, touch_i, reclaim_i, takeover_i = lifecycle(ks, break_i, low, high)
            rows.append({
                'symbol': symbol(path), 'combo_key': 'R4_RANGE_SSL_BREAKER_RECLAIM',
                'lifecycle_state': state,
                'range_low_a_idx': rg['low_a']['idx'], 'range_low_b_idx': rg['low_b']['idx'],
                'range_high_a_idx': rg['high_a']['idx'], 'range_high_b_idx': rg['high_b']['idx'],
                'range_ready_idx': rg['ready_idx'], 'range_floor': round(rg['floor'], 6),
                'range_ceiling': round(rg['ceiling'], 6),
                'sweep_idx': sweep_i, 'sweep_date': day(ks[sweep_i]),
                'event_idx': break_i, 'event_date': day(ks[break_i]), 'event_type': 'RANGE_HIGH_BOS',
                'poi_idx': poi_i, 'poi_date': day(ks[poi_i]), 'poi_type': 'FRESH_BEARISH_BREAKER',
                'zone_low': round(low, 6), 'zone_high': round(high, 6),
                'strict_lifecycle_start_idx': break_i,
                'touch_idx': '' if touch_i is None else touch_i,
                'reclaim_idx': '' if reclaim_i is None else reclaim_i,
                'takeover_idx': '' if takeover_i is None else takeover_i,
                'takeover_date': day(ks[takeover_i]) if state == 'TAKEOVER_CONFIRMED' else '',
                'semantic_contract': 'confirmed two-sided balance -> SSL below floor -> close reclaim inside range -> close break range ceiling -> fresh bearish breaker at/after SSL -> first touch/reclaim/hold',
                'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
            })
    # A market event is unique by symbol + break + POI.  Multiple overlapping
    # balance descriptions must not manufacture repeated candidates.  Select the
    # most recently confirmed balance, a source-only deterministic preference.
    unique = {}
    for row in rows:
        key = (row['symbol'], row['event_idx'], row['poi_idx'])
        rank = (int(row['range_ready_idx']), int(row['range_low_b_idx']), int(row['range_low_a_idx']))
        if key not in unique or rank > unique[key][0]:
            unique[key] = (rank, row)
    rows = [item[1] for item in unique.values()]
    # One stock can only create one next-session execution identity.  If distinct
    # events converge on the same takeover date, retain the later event because
    # it is the last source-visible structure before that decision point.
    execution_unique = {}
    non_takeover = []
    for row in rows:
        if row['lifecycle_state'] != 'TAKEOVER_CONFIRMED':
            non_takeover.append(row)
            continue
        key = (row['symbol'], row['takeover_idx'])
        rank = (int(row['event_idx']), int(row['poi_idx']), int(row['sweep_idx']))
        if key not in execution_unique or rank > execution_unique[key][0]:
            execution_unique[key] = (rank, row)
    rows = non_takeover + [item[1] for item in execution_unique.values()]
    stages = Counter(r['lifecycle_state'] for r in rows)
    yearly = Counter(r['takeover_date'][:4] for r in rows if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED')
    fields = list(rows[0]) if rows else ['symbol']
    with (OUT / 'v423_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    support_pass = all(yearly[y] >= 40 for y in ('2023', '2024', '2025', '2026'))
    report = {
        'version': 'V423_RANGE_ACCUMULATION_BREAKER_GENERATOR_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'contract': 'R4: confirmed two-sided balance -> SSL -> range reclaim -> range-high BOS -> fresh bearish breaker at/after SSL -> first touch/reclaim/hold',
        'qualitative_distinction': 'Requires a pre-existing two-sided balance and breaks its range ceiling; R1/R2/R3 do not require this accumulated balance-state source.',
        'counts': dict(counts), 'candidates': len(rows), 'lifecycle': dict(stages),
        'takeover_by_year': dict(yearly),
        'fixed_pre_outcome_gate': {'minimum_takeovers_per_year': 40, 'minimum_total_takeovers': 160},
        'pre_outcome_support_pass': support_pass,
        'invariants': {
            'all_non_tradable': all(r['tradable'] == 'false' for r in rows),
            'no_outcomes': all(r['outcome_fields_present'] == 'false' for r in rows),
            'no_entries_exits_or_marks_created': True,
        },
        'decision': ('R4_SUPPORT_GATE_PASS__ELIGIBLE_FOR_ONE_FROZEN_T1_MARK_REPLAY' if support_pass else 'R4_INSUFFICIENT_FULL_HISTORY_SUPPORT__NO_OUTCOME_REPLAY_OR_THRESHOLD_MINING'),
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v423_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v423_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
