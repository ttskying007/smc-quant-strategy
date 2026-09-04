#!/usr/bin/env python3
"""V425: one frozen T+1 diagnostic replay of independently audited V423 R4 seeds."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
AUD, KDIR = ROOT / 'smc_audit', ROOT / 'kline_cache'
SOURCE = AUD / 'v423_range_accumulation_breaker_latest.json'
INTEGRITY = AUD / 'v424_range_accumulation_breaker_integrity_latest.json'
OUT = AUD / f'v425_range_accumulation_breaker_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v425_range_accumulation_breaker_frozen_t1_replay_latest.json'
HORIZONS, YEARS = (5, 10, 20), ('2023', '2024', '2025', '2026')
GATE = {'min_year_n': 40, 'min_positive_pct': 50.0, 'min_avg_mark_pct': 0.0, 'max_zone_invalidated_pct': 30.0}


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


def pct(price, entry): return (price / entry - 1) * 100 if entry else 0.0


def metrics(rows, horizon):
    rows = [r for r in rows if r[f'mark_{horizon}d_pct'] is not None]
    if not rows: return {'n': 0}
    marks = [r[f'mark_{horizon}d_pct'] for r in rows]
    return {
        'n': len(rows),
        'positive_pct': round(sum(x > 0 for x in marks) / len(rows) * 100, 2),
        'avg_mark_pct': round(mean(marks), 4),
        'median_mark_pct': round(median(marks), 4),
        'zone_invalidated_pct': round(sum(r[f'zone_invalid_{horizon}d'] for r in rows) / len(rows) * 100, 2),
        'avg_mae_pct': round(mean(r[f'mae_{horizon}d_pct'] for r in rows), 4),
    }


def passes(x):
    return (x.get('n', 0) >= GATE['min_year_n'] and x['positive_pct'] >= GATE['min_positive_pct']
            and x['avg_mark_pct'] >= GATE['min_avg_mark_pct'] and x['zone_invalidated_pct'] <= GATE['max_zone_invalidated_pct'])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source, integrity = json.loads(SOURCE.read_text()), json.loads(INTEGRITY.read_text())
    if not integrity.get('pass'):
        raise RuntimeError('V424 integrity gate did not pass; frozen replay forbidden')
    with Path(source['artifacts']['rows']).open(newline='') as handle:
        seeds = [r for r in csv.DictReader(handle) if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED']
    cache, rows, skipped = {}, [], Counter()
    for seed in seeds:
        sym = seed['symbol']
        if sym not in cache: cache[sym] = load(sym)
        bars = cache[sym]
        takeover_i = next((i for i, b in enumerate(bars) if day(b) == seed['takeover_date']), None)
        if takeover_i is None or takeover_i + 1 >= len(bars):
            skipped['NO_T1_ENTRY_BAR'] += 1; continue
        entry_i, entry = takeover_i + 1, f(bars[takeover_i + 1]['o'])
        if entry <= 0:
            skipped['INVALID_T1_OPEN'] += 1; continue
        row = {k: seed[k] for k in ('symbol', 'combo_key', 'sweep_date', 'event_date', 'poi_date', 'poi_type', 'zone_low', 'zone_high', 'takeover_date')}
        row.update({'entry_date': day(bars[entry_i]), 'entry_price': round(entry, 6), 't1_violation': False})
        for horizon in HORIZONS:
            end_i = entry_i + horizon
            if end_i >= len(bars):
                row.update({f'mark_{horizon}d_pct': None, f'mae_{horizon}d_pct': None, f'zone_invalid_{horizon}d': None})
                continue
            window = bars[entry_i + 1:end_i + 1]
            row[f'mark_{horizon}d_pct'] = round(pct(f(bars[end_i]['c']), entry), 6)
            row[f'mae_{horizon}d_pct'] = round(pct(min(f(b['l']) for b in window), entry), 6)
            row[f'zone_invalid_{horizon}d'] = any(f(b['c']) < f(seed['zone_low']) for b in window)
        rows.append(row)
    overall = {f'{h}d': metrics(rows, h) for h in HORIZONS}
    annual = {f'{h}d': {year: metrics([r for r in rows if r['entry_date'][:4] == year], h) for year in YEARS} for h in (5, 10)}
    annual_pass = {f'{h}d': all(passes(x) for x in annual[f'{h}d'].values()) for h in (5, 10)}
    with (OUT / 'v425_mark_rows.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['symbol'])
        writer.writeheader(); writer.writerows(rows)
    yearly_rows = [{'horizon_sessions': h, 'entry_year': y, **m, 'year_gate_pass': passes(m)} for h in (5, 10) for y, m in annual[f'{h}d'].items()]
    with (OUT / 'v425_yearly_metrics.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(yearly_rows[0]) if yearly_rows else ['horizon_sessions'])
        writer.writeheader(); writer.writerows(yearly_rows)
    report = {
        'version': 'V425_RANGE_ACCUMULATION_BREAKER_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SOURCE), 'integrity_gate': str(INTEGRITY),
        'frozen_signal_contract': source['contract'],
        'frozen_execution_contract': 'TAKEOVER_CONFIRMED only -> next session open; marks exclude entry session; no TP/SL/threshold/exit search',
        'diagnostic_contract': 'fixed 5/10/20-session close mark, adverse excursion, and close-below-zone incidence only',
        'predeclared_annual_gate': GATE,
        'takeover_seeds': len(seeds), 'rows_with_t1_entry': len(rows), 'skipped': dict(skipped),
        'overall_quality': overall, 'annual_stability': annual, 'annual_gate_pass': annual_pass,
        'invariants': {'all_t1_compliant': all(not r['t1_violation'] for r in rows), 'no_execution_parameter_search': True, 'no_production_promotion': True, 'input_integrity_pass': integrity['pass']},
        'decision': 'R4_FROZEN_DIAGNOSTIC_COMPLETE__PROMOTION_ONLY_IF_ANNUAL_GATE_PASSES',
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v425_mark_rows.csv'), 'yearly_metrics': str(OUT / 'v425_yearly_metrics.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v425_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__': main()
