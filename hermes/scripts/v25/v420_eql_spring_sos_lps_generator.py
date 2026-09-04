#!/usr/bin/env python3
"""V420 no-write EQL spring -> SOS -> LPS lifecycle generator.

A new pure-structure story, independent of V409's generic swing sweep:
confirmed equal-low liquidity pool -> later spring sweep/reclaim -> break above the
pre-spring range high (SOS) -> fresh spring-wick demand retest/reclaim/hold.
No entries, exits, prices after takeover, PnL, or outcomes are created.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
OUT = AUD / f'v420_eql_spring_sos_lps_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v420_eql_spring_sos_lps_latest.json'


def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(b):
    return ''.join(c for c in str(b.get('t') or b.get('date') or '') if c.isdigit())[:8]


def load(path):
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))], key=day)


def symbol(path):
    p = path.name.replace('_daily_750.json', '').split('_')
    return f'{p[0]}.{p[1]}' if len(p) == 2 else path.stem


def pivots(ks):
    lows, highs = [], []
    for i in range(3, len(ks) - 3):
        lo, hi = f(ks[i]['l']), f(ks[i]['h'])
        if all(lo < f(ks[j]['l']) for j in range(i - 3, i + 4) if j != i):
            lows.append({'idx': i, 'price': lo, 'confirm_idx': i + 3})
        if all(hi > f(ks[j]['h']) for j in range(i - 3, i + 4) if j != i):
            highs.append({'idx': i, 'price': hi, 'confirm_idx': i + 3})
    return lows, highs


def lifecycle(ks, start, low, high):
    touch = reclaim = None
    for i in range(start + 1, min(len(ks), start + 31)):
        lo, cl = f(ks[i]['l']), f(ks[i]['c'])
        if cl < low:
            return 'CANCEL_ZONE_INVALIDATED', i, touch, reclaim
        if touch is None:
            if lo <= high:
                touch = i
            continue
        if reclaim is None:
            if cl > high:
                reclaim = i
            continue
        if cl > high and lo >= low:
            return 'TAKEOVER_CONFIRMED', i, touch, reclaim
    full = start + 30 < len(ks)
    if touch is None:
        return ('EXPIRE_NO_TOUCH_30B' if full else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None:
        return ('EXPIRE_NO_RECLAIM_30B' if full else 'WAIT_RECLAIM_UNOBSERVED'), None, touch, None
    return ('EXPIRE_NO_HOLD_30B' if full else 'WAIT_HOLD_UNOBSERVED'), None, touch, reclaim


def scan(path_str):
    path, rows, counts = Path(path_str), [], Counter()
    ks = load(path)
    if len(ks) < 80:
        return rows, counts
    sym, (lows, _) = symbol(path), pivots(ks)
    seen_springs = set()
    for a, b in zip(lows, lows[1:]):
        gap = b['idx'] - a['idx']
        if not 10 <= gap <= 60:
            continue
        pool_low, pool_high = min(a['price'], b['price']), max(a['price'], b['price'])
        if pool_high / pool_low - 1 > 0.01:
            continue
        for spring in range(b['confirm_idx'] + 1, min(len(ks), b['confirm_idx'] + 31)):
            if spring in seen_springs:
                continue
            sb = ks[spring]
            if not (f(sb['l']) < pool_low * 0.997 and f(sb['c']) > pool_high * 1.001):
                continue
            range_high = max(f(x['h']) for x in ks[a['idx']:spring])
            if f(sb['c']) > range_high * 1.002:
                counts['SPRING_ALREADY_SOS_SAME_BAR'] += 1
                continue
            sos = next((i for i in range(spring + 1, min(len(ks), spring + 21))
                        if f(ks[i]['c']) > range_high * 1.002), None)
            if sos is None:
                counts['SPRING_NO_SOS_20B'] += 1
                continue
            zone_low, zone_high = f(sb['l']), min(f(sb['o']), f(sb['c']))
            if any(f(ks[i]['l']) <= zone_high for i in range(spring + 1, sos + 1)):
                counts['SPRING_POI_MITIGATED_BEFORE_SOS'] += 1
                continue
            status, end_i, touch, reclaim = lifecycle(ks, sos, zone_low, zone_high)
            seen_springs.add(spring)
            date_at = lambda i: day(ks[i]) if i is not None else ''
            rows.append({
                'symbol': sym, 'combo_key': 'R3_EQL_SPRING_SOS_LPS',
                'pool_low1_idx': a['idx'], 'pool_low1_date': date_at(a['idx']), 'pool_low1_price': round(a['price'], 6),
                'pool_low2_idx': b['idx'], 'pool_low2_date': date_at(b['idx']), 'pool_low2_price': round(b['price'], 6),
                'pool_confirm_idx': b['confirm_idx'], 'pool_confirm_date': date_at(b['confirm_idx']),
                'spring_idx': spring, 'spring_date': date_at(spring), 'spring_low': round(f(sb['l']), 6),
                'sos_idx': sos, 'sos_date': date_at(sos), 'range_high': round(range_high, 6),
                'zone_low': round(zone_low, 6), 'zone_high': round(zone_high, 6),
                'lifecycle_state': status,
                'touch_idx': '' if touch is None else touch, 'touch_date': date_at(touch),
                'reclaim_idx': '' if reclaim is None else reclaim, 'reclaim_date': date_at(reclaim),
                'takeover_idx': '' if status != 'TAKEOVER_CONFIRMED' else end_i,
                'takeover_date': date_at(end_i) if status == 'TAKEOVER_CONFIRMED' else '',
                'semantic_contract': 'confirmed EQL pool -> later spring -> later SOS -> fresh spring-wick POI -> touch -> reclaim -> hold',
                'tradable': 'false', 'buy_enabled': 'false', 'outcome_fields_present': 'false',
            })
            counts['SEMANTIC_CANDIDATE'] += 1
            counts[status] += 1
    counts['SYMBOL_SCANNED'] += 1
    return rows, counts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [str(p) for p in sorted(KDIR.glob('*_daily_750.json'))]
    rows, counts = [], Counter()
    with ProcessPoolExecutor(max_workers=12) as pool:
        for part, c in pool.map(scan, paths, chunksize=20):
            rows.extend(part); counts.update(c)
    fields = list(rows[0]) if rows else ['symbol', 'combo_key']
    row_path = OUT / 'v420_lifecycle_rows.csv'
    with row_path.open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)
    stages = Counter(r['lifecycle_state'] for r in rows)
    report = {
        'version': 'V420_EQL_SPRING_SOS_LPS_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'scope': 'new pure-structure semantic generator only; no entry, exit, PnL, marks, or promotion',
        'frozen_contract': {
            'liquidity_pool': 'two consecutive confirmed 3L/3R swing lows, 10..60 bars apart, price separation <=1%',
            'spring': 'after second pivot confirmation: wick below pool by 0.3%, close above pool by 0.1%, within 30 bars',
            'sos': 'later close > pre-spring range high by 0.2%, within 20 bars; same-bar compression rejected',
            'poi': 'spring wick [spring low, min(open,close)], untouched through SOS',
            'lps': 'post-SOS touch -> later close reclaim -> next-bar hold; close below spring low cancels',
        },
        'stage_counts': dict(counts), 'lifecycle': dict(stages),
        'takeover_confirmed': stages['TAKEOVER_CONFIRMED'],
        'takeover_rate_pct': round(stages['TAKEOVER_CONFIRMED'] / len(rows) * 100, 4) if rows else 0.0,
        'invariants': {'all_rows_non_tradable': all(r['tradable'] == 'false' for r in rows),
                       'no_outcome_fields': all(r['outcome_fields_present'] == 'false' for r in rows)},
        'decision': 'SEMANTIC_GENERATOR_READY__ONE_FROZEN_T1_STRUCTURAL_REPLAY_NEXT',
        'artifacts': {'out_dir': str(OUT), 'rows': str(row_path), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v420_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__':
    main()
