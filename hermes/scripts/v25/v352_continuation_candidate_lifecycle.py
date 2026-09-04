#!/usr/bin/env python3
"""V352 no-write continuation candidate lifecycle rebuild from V351 semantic seeds.

Lifecycle only: semantic seed -> touch -> reclaim -> hold-above-zone takeover,
or terminal cancellation.  It never creates entries, exits, PnL, or tradable picks.
"""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
KDIR, AUD = ROOT / 'kline_cache', ROOT / 'smc_audit'
SRC = AUD / 'v351_semantic_oracle_latest.json'
OUT = AUD / f"v352_continuation_lifecycle_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST = AUD / 'v352_continuation_lifecycle_latest.json'


def f(x):
    try:
        v = float(x); return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError): return 0.0


def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def bars(sym):
    try: raw = json.loads((KDIR / f"{sym.replace('.', '_')}_daily_750.json").read_text())
    except Exception: return []
    return sorted([b for b in raw if ds(b.get('t') or b.get('date'))], key=lambda b: ds(b.get('t') or b.get('date')))


def lifecycle(ks, seed):
    event, low, high = int(seed['event_idx']), f(seed['zone_low']), f(seed['zone_high'])
    touch = reclaim = None
    for i in range(event + 1, min(len(ks), event + 31)):
        b = ks[i]; lo, cl = f(b.get('l')), f(b.get('c'))
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
        if i > reclaim and cl > high and lo >= low:
            return 'TAKEOVER_CONFIRMED', i, touch, reclaim
    # A truncated right edge is an unresolved lifecycle, never an expiry.  Treating
    # it as an expiry would contaminate the current scanner state with false failures.
    full_window_observed = event + 30 < len(ks)
    if touch is None:
        return ('EXPIRE_NO_TOUCH_30B' if full_window_observed else 'WAIT_TOUCH_UNOBSERVED'), None, None, None
    if reclaim is None:
        return ('EXPIRE_NO_RECLAIM_30B' if full_window_observed else 'WAIT_RECLAIM_UNOBSERVED'), None, touch, None
    return ('EXPIRE_NO_HOLD_30B' if full_window_observed else 'WAIT_HOLD_UNOBSERVED'), None, touch, reclaim


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(SRC.read_text())
    seed_file = Path(report['artifacts']['seeds'])
    with seed_file.open() as src: raw_seeds = list(csv.DictReader(src))

    # An OB is one setup, not a new setup every time price breaks another swing
    # while that exact same OB remains the nearest opposite candle.  Canonicalize
    # by (symbol, ob_idx) before lifecycle processing; retain its first causal BOS.
    # This is an audit-only identity rule and does not alter V27 or production.
    seeds, seen_ob = [], set()
    for seed in sorted(raw_seeds, key=lambda x: (x['symbol'], int(x['event_idx']))):
        setup_id = (seed['symbol'], seed['ob_idx'])
        if setup_id not in seen_ob:
            seen_ob.add(setup_id)
            seeds.append(seed)

    cache, rows, counts, by_year = {}, [], Counter(), {}
    counts['RAW_SEMANTIC_SEEDS'] = len(raw_seeds)
    counts['UNIQUE_OB_SETUP_SEEDS'] = len(seeds)
    counts['SUPPRESSED_REUSED_OB_SEEDS'] = len(raw_seeds) - len(seeds)
    for seed in seeds:
        sym = seed['symbol']
        if sym not in cache: cache[sym] = bars(sym)
        ks = cache[sym]
        if not ks: counts['CANCEL_MISSING_KLINE'] += 1; continue
        status, state_i, touch_i, reclaim_i = lifecycle(ks, seed)
        counts['SEMANTIC_VALID_CONTINUATION_SEED'] += 1; counts[status] += 1
        state_date = ds(ks[state_i].get('t') or ks[state_i].get('date')) if state_i is not None else ''
        year = state_date[:4] or str(seed['event_date'])[:4]
        by_year.setdefault(year, Counter())['seeds'] += 1
        by_year[year][status] += 1
        rows.append({**seed, 'lifecycle_state': status, 'touch_date': ds(ks[touch_i].get('t') or ks[touch_i].get('date')) if touch_i is not None else '',
                     'reclaim_date': ds(ks[reclaim_i].get('t') or ks[reclaim_i].get('date')) if reclaim_i is not None else '',
                     'takeover_date': state_date if status == 'TAKEOVER_CONFIRMED' else '',
                     'lifecycle_end_date': state_date, 'tradable': 'false', 'buy_enabled': 'false',
                     'no_entry_or_outcome_fields': 'true'})
    fields = list(rows[0]) if rows else ['symbol','lifecycle_state']
    with (OUT / 'v352_lifecycle_rows.csv').open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    yearly = []
    for year, x in sorted(by_year.items()):
        n = x['seeds']; takeover = x['TAKEOVER_CONFIRMED']
        yearly.append({'year': year, **dict(x), 'takeover_rate_pct': round(takeover / n * 100, 2) if n else 0})
    result = {'version': 'V352_CONTINUATION_CANDIDATE_LIFECYCLE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'source_contract': 'V351 semantic-valid daily BOS continuation + event-anchored backward OB',
              'lifecycle_contract': 'seed -> touch(wick<=zone_high) -> reclaim(close>zone_high) -> takeover(next hold above zone); close<zone_low cancels',
              'stage_counts': dict(counts), 'yearly_lifecycle': yearly,
              'invariants': {'no_entries_created': True, 'no_exit_or_pnl_fields': True, 'all_rows_non_tradable': all(r['tradable'] == 'false' for r in rows)},
              'decision': 'LIFECYCLE_EVIDENCE_READY__60MIN_BLOCKED_PENDING_STABILITY_GATE',
              'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v352_lifecycle_rows.csv'), 'latest': str(LATEST)}}
    text = json.dumps(result, ensure_ascii=False, indent=2); (OUT / 'v352_report.json').write_text(text); LATEST.write_text(text)
    print(text)

if __name__ == '__main__': main()
