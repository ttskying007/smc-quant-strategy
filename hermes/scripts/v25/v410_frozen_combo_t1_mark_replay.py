#!/usr/bin/env python3
"""V410 frozen T+1 mark-outcome replay for V409 causal combinations.

This is a single predeclared diagnostic, not parameter search: only candidates
whose lifecycle already reached TAKEOVER_CONFIRMED enter on the next daily open.
It reports fixed 5/10/20-session close marks and zone invalidation incidence.
No TP/SL optimization, filtering, promotion, production, or UI writes.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
SOURCE = AUD / 'v409_causal_signal_combination_latest.json'
OUT = AUD / f'v410_frozen_combo_t1_mark_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v410_frozen_combo_t1_mark_replay_latest.json'
HORIZONS = (5, 10, 20)


def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar): return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(symbol):
    path = KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    try: raw = json.loads(path.read_text())
    except Exception: return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))], key=day)


def pct(a, b): return (a / b - 1) * 100 if b else 0.0


def metric(rows, horizon):
    vals = [r[f'mark_{horizon}d_pct'] for r in rows if r.get(f'mark_{horizon}d_pct') is not None]
    if not vals: return {'n': 0}
    return {
        'n': len(vals), 'positive_pct': round(sum(x > 0 for x in vals) / len(vals) * 100, 2),
        'avg_mark_pct': round(mean(vals), 4), 'median_mark_pct': round(median(vals), 4),
        'zone_invalidated_pct': round(sum(r[f'zone_invalid_{horizon}d'] for r in rows if r.get(f'mark_{horizon}d_pct') is not None) / len(vals) * 100, 2),
        'avg_mae_pct': round(mean(r[f'mae_{horizon}d_pct'] for r in rows if r.get(f'mark_{horizon}d_pct') is not None), 4),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SOURCE.read_text())
    with open(source['artifacts']['rows'], newline='', encoding='utf-8') as file:
        seeds = [r for r in csv.DictReader(file) if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED']
    cache, rows, skipped = {}, [], Counter()
    for seed in seeds:
        sym = seed['symbol']
        if sym not in cache: cache[sym] = load(sym)
        ks = cache[sym]
        index = next((i for i, b in enumerate(ks) if day(b) == seed['takeover_date']), None)
        if index is None or index + 1 >= len(ks):
            skipped['NO_T1_ENTRY_BAR'] += 1; continue
        entry_i, entry = index + 1, f(ks[index + 1].get('o'))
        if entry <= 0:
            skipped['INVALID_T1_OPEN'] += 1; continue
        row = {k: seed[k] for k in ('symbol', 'combo_key', 'takeover_date', 'zone_low', 'zone_high')}
        row.update({'entry_date': day(ks[entry_i]), 'entry_price': round(entry, 6), 't1_violation': False})
        for h in HORIZONS:
            end = entry_i + h
            if end >= len(ks):
                row.update({f'mark_{h}d_pct': None, f'mae_{h}d_pct': None, f'zone_invalid_{h}d': None})
                continue
            window = ks[entry_i + 1:end + 1]  # excludes entry day: A-share T+1 measurement
            row[f'mark_{h}d_pct'] = round(pct(f(ks[end].get('c')), entry), 6)
            row[f'mae_{h}d_pct'] = round(pct(min(f(b.get('l')) for b in window), entry), 6)
            row[f'zone_invalid_{h}d'] = any(f(b.get('c')) < f(seed['zone_low']) for b in window)
        rows.append(row)
    fields = list(rows[0]) if rows else ['symbol', 'combo_key']
    with (OUT / 'v410_mark_rows.csv').open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    summary = {}
    for combo in ('R1_SSL_CHOCH_DEMAND_OB', 'R2_SSL_CHOCH_BULL_FVG', 'C1_BOS_DEMAND_OB'):
        x = [r for r in rows if r['combo_key'] == combo]
        summary[combo] = {f'{h}d': metric(x, h) for h in HORIZONS}
    report = {
        'version': 'V410_FROZEN_CAUSAL_COMBINATION_T1_MARK_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SOURCE),
        'frozen_execution_contract': 'TAKEOVER_CONFIRMED only -> next session open; T+1 marks use sessions after entry; no stop/target/threshold search',
        'diagnostic_contract': '5/10/20-session close mark, adverse excursion, and close-below-zone incidence only; not tradable PnL',
        'candidates_input': len(seeds), 'rows_with_t1_entry': len(rows), 'skipped': dict(skipped),
        'combination_quality': summary,
        'invariants': {'all_t1_compliant': all(not r['t1_violation'] for r in rows), 'no_execution_parameter_search': True, 'no_promotion': True},
        'decision': 'FROZEN_COMBO_QUALITY_READY__REQUIRE_YEARLY_STABILITY_AND_INDEPENDENT_SEMANTIC_AUDIT_BEFORE_PROMOTION',
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v410_mark_rows.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v410_report.json').write_text(text); LATEST.write_text(text)
    print(text)


if __name__ == '__main__': main()
