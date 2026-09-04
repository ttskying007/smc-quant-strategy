#!/usr/bin/env python3
"""V287 no-write: event-time rolling adaptive regime router.

V286 year-walk-forward proved parent market/industry regime helps but stale yearly
rules still fail in 2026/monthly tails.  This script tests the next concrete
hypothesis: select V280 grammar surfaces using only event-time rolling history
before each entry date.  Same-date events are evaluated before being added to the
history, so no same-day outcome leakage is possible.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V286_SCRIPT = BASE / 'scripts/v25/v286_regime_parent_router_walkforward.py'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v287_event_time_rolling_regime_router_no_write_{TS}'
LATEST = AUDIT / 'v287_event_time_rolling_regime_router_latest.json'
TEST_YEARS = {'2024', '2025', '2026'}

spec = importlib.util.spec_from_file_location('v286mod', V286_SCRIPT)
v286 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(v286)


def parse_dt(s: str) -> datetime:
    return datetime.strptime(v286.dn(s), '%Y%m%d')


def sub(a: dict[str, Any], r: dict[str, Any]) -> None:
    """Inverse of v286.add for rolling-window aggregates.

    Train-symbol count is diagnostic only, so symbols are not removed from the
    set. Thresholds use n/wr/avg/month tails; selected-result metrics remain
    exact because they use normal v286.add.
    """
    pnl = v286.sf(r.get('pnl'), 0.0)
    y = str(r.get('year') or v286.dn(r.get('entry_date'))[:4])
    m = v286.dn(r.get('entry_date'))[:6]
    reason = str(r.get('reason') or '')
    a['n'] -= 1
    a['wins'] -= pnl > 0
    a['sum'] -= pnl
    a['loss'] -= pnl <= 0
    a['micro'] -= 0 < pnl < 1
    a['tp'] -= reason == 'TP'
    a['sl'] -= reason == 'SL'
    a['time'] -= reason.startswith('TIME')
    a['years'][y][0] -= 1
    a['years'][y][1] -= pnl > 0
    if m:
        a['months'][m][0] -= 1
        a['months'][m][1] -= pnl > 0


def passes(m: dict[str, Any], grid: dict[str, Any]) -> bool:
    if m.get('n', 0) < grid['min_n']:
        return False
    if m.get('wr', 0) < grid['min_wr'] or m.get('avg', -999) < grid['min_avg']:
        return False
    # If the rolling window spans enough months, reject rules with deeply unstable tails.
    if m.get('months', 0) >= grid.get('min_months_for_tail', 99):
        tail = m.get('min_month_wr_n20')
        if tail is not None and tail < grid.get('min_month_wr', 0):
            return False
    return True


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = v286.enrich_rows()
    rows.sort(key=lambda r: (v286.dn(r['entry_date']), r['symbol'], r['family']))
    baseline = v286.blank()
    for r in rows:
        if r['year'] in TEST_YEARS:
            v286.add(baseline, r)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[v286.dn(r['entry_date'])].append(r)
    dates = sorted(groups)

    grids = [
        {'name': 'roll90_n40_wr57_avg10', 'window_days': 90, 'min_n': 40, 'min_wr': 57.0, 'min_avg': 1.0, 'min_months_for_tail': 99, 'min_month_wr': 0.0},
        {'name': 'roll180_n80_wr55_avg10_tail35', 'window_days': 180, 'min_n': 80, 'min_wr': 55.0, 'min_avg': 1.0, 'min_months_for_tail': 3, 'min_month_wr': 35.0},
        {'name': 'roll270_n120_wr54_avg08_tail38', 'window_days': 270, 'min_n': 120, 'min_wr': 54.0, 'min_avg': 0.8, 'min_months_for_tail': 4, 'min_month_wr': 38.0},
        {'name': 'roll360_n180_wr53_avg08_tail40', 'window_days': 360, 'min_n': 180, 'min_wr': 53.0, 'min_avg': 0.8, 'min_months_for_tail': 5, 'min_month_wr': 40.0},
    ]

    # One independent rolling history per grid to allow different window pruning.
    histories = {
        g['name']: defaultdict(lambda: {'dq': deque(), 'agg': v286.blank()}) for g in grids
    }
    results = {g['name']: {'grid': g, 'agg': v286.blank(), 'by_year': {y: v286.blank() for y in sorted(TEST_YEARS)},
                           'selected_by_year': defaultdict(int), 'rule_hits': defaultdict(int)} for g in grids}

    out_rows = OUT / 'v287_selected_rows.csv'
    with out_rows.open('w', newline='') as fh:
        base_fields = sorted({k for r in rows for k in r.keys()})
        fields = base_fields + ['grid', 'matched_dim', 'matched_val', 'train_n', 'train_wr', 'train_avg', 'train_min_month_wr_n20']
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for d in dates:
            day = parse_dt(d)
            todays = groups[d]
            # Evaluate all rows for this day before adding today's outcomes to rolling history.
            for grid in grids:
                hists = histories[grid['name']]
                cutoff = day - timedelta(days=grid['window_days'])
                for r in todays:
                    if r['year'] not in TEST_YEARS:
                        continue
                    best = None
                    for key in v286.row_keys(r):
                        state = hists[key]
                        dq = state['dq']
                        agg = state['agg']
                        while dq and dq[0][0] < cutoff:
                            _, old = dq.popleft()
                            sub(agg, old)
                        if not dq:
                            continue
                        m = v286.metrics(agg)
                        if passes(m, grid):
                            score = (m['avg'], m['wr'], m.get('min_month_wr_n20') or 0, math.log1p(m['n']))
                            if best is None or score > best['score']:
                                best = {'key': key, 'metrics': m, 'score': score}
                    if best is None:
                        continue
                    res = results[grid['name']]
                    v286.add(res['agg'], r)
                    v286.add(res['by_year'][r['year']], r)
                    res['selected_by_year'][r['year']] += 1
                    res['rule_hits'][best['key']] += 1
                    out = dict(r)
                    m = best['metrics']
                    out.update({'grid': grid['name'], 'matched_dim': best['key'][0], 'matched_val': best['key'][1],
                                'train_n': m.get('n'), 'train_wr': m.get('wr'), 'train_avg': m.get('avg'),
                                'train_min_month_wr_n20': m.get('min_month_wr_n20')})
                    writer.writerow(out)
            # Only after evaluation, add today's rows to every grid history.
            for grid in grids:
                hists = histories[grid['name']]
                for r in todays:
                    dt = parse_dt(r['entry_date'])
                    for key in v286.row_keys(r):
                        state = hists[key]
                        state['dq'].append((dt, r))
                        v286.add(state['agg'], r)

    selectors = []
    for name, res in results.items():
        top_hits = sorted(res['rule_hits'].items(), key=lambda kv: kv[1], reverse=True)[:20]
        selectors.append({
            'grid': res['grid'],
            'selected_rows_by_year': dict(res['selected_by_year']),
            'walk_forward': v286.metrics(res['agg']),
            'by_year_detail': {y: v286.metrics(a) for y, a in res['by_year'].items()},
            'top_matched_rules': [{'dim': k[0], 'val': k[1], 'hits': v} for k, v in top_hits],
        })

    summary = {
        'version': 'V287_EVENT_TIME_ROLLING_REGIME_ROUTER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': {'v286_script': str(V286_SCRIPT), 'v280_events': str(v286.EVENTS), 'industry_map': str(v286.INDMAP)},
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'leakage_guard': 'same-date groups evaluated before outcomes are appended to rolling histories',
        'inputs': {'rows': len(rows), 'symbols': len({r['symbol'] for r in rows}), 'test_years': sorted(TEST_YEARS)},
        'baseline_test_years': v286.metrics(baseline),
        'rolling_selectors': selectors,
        'artifacts': {'selected_rows': str(out_rows), 'out_dir': str(OUT)},
    }
    (OUT / 'v287_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'out': str(OUT), 'latest': str(LATEST), 'baseline': summary['baseline_test_years'], 'selectors': selectors}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
