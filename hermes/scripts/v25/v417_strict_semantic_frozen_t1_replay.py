#!/usr/bin/env python3
"""V417: one frozen T+1 mark replay of V416 strict semantic candidates.

This repairs V409's lifecycle-label defect without changing a single execution
parameter: TAKEOVER_CONFIRMED -> next-session open; then 5/10/20-session marks.
It is diagnostic only, creates no tradable output, and applies V411's original
annual stability gate unchanged.
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
SOURCE = AUD / 'v416_strict_semantic_combination_rebuild_latest.json'
OUT = AUD / f'v417_strict_semantic_frozen_t1_replay_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v417_strict_semantic_frozen_t1_replay_latest.json'
COMBOS = ('R1_SSL_CHOCH_DEMAND_OB', 'R2_SSL_CHOCH_BULL_FVG', 'C1_BOS_DEMAND_OB')
HORIZONS, YEARS = (5, 10, 20), ('2023', '2024', '2025', '2026')
GATE = {'min_year_n': 40, 'min_positive_pct': 50.0, 'min_avg_mark_pct': 0.0, 'max_zone_invalidated_pct': 30.0}


def f(x: object) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def day(bar: dict) -> str:
    return ''.join(c for c in str(bar.get('t') or bar.get('date') or '') if c.isdigit())[:8]


def load(symbol: str) -> list[dict]:
    try:
        raw = json.loads((KDIR / f"{symbol.replace('.', '_')}_daily_750.json").read_text())
    except Exception:
        return []
    return sorted([b for b in raw if day(b) and all(f(b.get(k)) > 0 for k in ('o', 'h', 'l', 'c'))], key=day)


def pct(a: float, b: float) -> float:
    return (a / b - 1) * 100 if b else 0.0


def metrics(rows: list[dict], horizon: int) -> dict:
    valid = [r for r in rows if r[f'mark_{horizon}d_pct'] is not None]
    if not valid:
        return {'n': 0}
    marks = [r[f'mark_{horizon}d_pct'] for r in valid]
    return {
        'n': len(valid),
        'positive_pct': round(sum(x > 0 for x in marks) / len(valid) * 100, 2),
        'avg_mark_pct': round(mean(marks), 4),
        'median_mark_pct': round(median(marks), 4),
        'zone_invalidated_pct': round(sum(r[f'zone_invalid_{horizon}d'] for r in valid) / len(valid) * 100, 2),
        'avg_mae_pct': round(mean(r[f'mae_{horizon}d_pct'] for r in valid), 4),
    }


def passes(x: dict) -> bool:
    return (x.get('n', 0) >= GATE['min_year_n']
            and x['positive_pct'] >= GATE['min_positive_pct']
            and x['avg_mark_pct'] >= GATE['min_avg_mark_pct']
            and x['zone_invalidated_pct'] <= GATE['max_zone_invalidated_pct'])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(SOURCE.read_text())
    with Path(source['artifacts']['rows']).open(newline='', encoding='utf-8') as handle:
        seeds = [r for r in csv.DictReader(handle) if r['lifecycle_state'] == 'TAKEOVER_CONFIRMED']
    cache: dict[str, list[dict]] = {}
    rows, skipped = [], Counter()
    for seed in seeds:
        sym = seed['symbol']
        if sym not in cache:
            cache[sym] = load(sym)
        bars = cache[sym]
        takeover_i = next((i for i, b in enumerate(bars) if day(b) == seed['takeover_date']), None)
        if takeover_i is None or takeover_i + 1 >= len(bars):
            skipped['NO_T1_ENTRY_BAR'] += 1
            continue
        entry_i, entry = takeover_i + 1, f(bars[takeover_i + 1].get('o'))
        if entry <= 0:
            skipped['INVALID_T1_OPEN'] += 1
            continue
        row = {key: seed[key] for key in ('symbol', 'combo_key', 'sweep_date', 'event_date', 'poi_date', 'poi_type', 'zone_low', 'zone_high', 'takeover_date')}
        row.update({'entry_date': day(bars[entry_i]), 'entry_price': round(entry, 6), 't1_violation': False})
        for horizon in HORIZONS:
            end_i = entry_i + horizon
            if end_i >= len(bars):
                row.update({f'mark_{horizon}d_pct': None, f'mae_{horizon}d_pct': None, f'zone_invalid_{horizon}d': None})
                continue
            window = bars[entry_i + 1:end_i + 1]
            row[f'mark_{horizon}d_pct'] = round(pct(f(bars[end_i].get('c')), entry), 6)
            row[f'mae_{horizon}d_pct'] = round(pct(min(f(b.get('l')) for b in window), entry), 6)
            row[f'zone_invalid_{horizon}d'] = any(f(b.get('c')) < f(seed['zone_low']) for b in window)
        rows.append(row)

    with (OUT / 'v417_mark_rows.csv').open('w', newline='') as handle:
        fields = list(rows[0]) if rows else ['symbol', 'combo_key']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

    overall, annual = {}, {}
    annual_rows, total_passes = [], 0
    for combo in COMBOS:
        selected = [r for r in rows if r['combo_key'] == combo]
        overall[combo] = {f'{h}d': metrics(selected, h) for h in HORIZONS}
        annual[combo] = {}
        for horizon in (5, 10):
            by_year = {year: metrics([r for r in selected if r['entry_date'][:4] == year], horizon) for year in YEARS}
            passed = all(passes(x) for x in by_year.values())
            total_passes += int(passed)
            annual[combo][f'{horizon}d'] = {'by_year': by_year, 'stability_gate_pass': passed}
            for year, values in by_year.items():
                annual_rows.append({'combo_key': combo, 'horizon_sessions': horizon, 'entry_year': year, **values, 'year_gate_pass': passes(values)})
    with (OUT / 'v417_yearly_metrics.csv').open('w', newline='') as handle:
        fields = list(annual_rows[0]) if annual_rows else ['combo_key', 'entry_year']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(annual_rows)

    report = {
        'version': 'V417_STRICT_SEMANTIC_FROZEN_T1_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'source': str(SOURCE),
        'semantic_correction': 'V415/V416 exclude pre-event mitigated or invalidated OBs and begin FVG lifecycle after its creation bar.',
        'frozen_execution_contract': 'TAKEOVER_CONFIRMED only -> next session open; marks exclude entry session; no TP/SL/threshold/exit search',
        'diagnostic_contract': 'fixed 5/10/20 session close mark, adverse excursion, and close-below-zone incidence only',
        'predeclared_annual_gate': GATE,
        'candidates_input': len(seeds), 'rows_with_t1_entry': len(rows), 'skipped': dict(skipped),
        'combination_quality': overall, 'annual_stability': annual, 'combination_horizon_passes': total_passes,
        'invariants': {
            'all_t1_compliant': all(not r['t1_violation'] for r in rows),
            'no_execution_parameter_search': True,
            'no_production_promotion': True,
            'no_outcome_fields_in_input': source['invariants']['no_outcome_fields'],
        },
        'decision': 'STRICT_SEMANTIC_COMBINATION_DIAGNOSTIC_COMPLETE__DO_NOT_PROMOTE_UNLESS_FROZEN_ANNUAL_GATE_PASSES',
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v417_mark_rows.csv'), 'yearly_metrics': str(OUT / 'v417_yearly_metrics.csv'), 'latest': str(LATEST)},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v417_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
