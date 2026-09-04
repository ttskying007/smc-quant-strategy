#!/usr/bin/env python3
"""V395 no-write PIT margin-financing information-layer gate for fixed V381 trades.

Uses only the last completed exchange session strictly before each intraday hold.
It never regenerates a candidate, modifies execution, or writes production data.
"""
from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
SRC = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_no_write_20260712_110522/v381_trades.csv'
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUD / f'v395_pit_margin_financing_no_write_{STAMP}'
LATEST = AUD / 'v395_pit_margin_financing_latest.json'

# Predeclared discovery gate. Passing this would permit a later independent replay,
# not production promotion.
DISCOVERY_GATE = {
    'n_min': 300,
    'year_n_min': 40,
    'wr_uplift_pp_min': 5.0,
    'avg_pnl_uplift_pp_min': 1.0,
    'min_year_wr_uplift_pp_min': 3.0,
    'source_date_coverage_pct_min': 95.0,
}


def d8(value: str) -> str:
    return ''.join(c for c in str(value) if c.isdigit())[:8]


def pct(n: float, d: float) -> float:
    return round(n / d * 100, 4) if d else 0.0


def metrics(rows: list[dict]) -> dict:
    if not rows:
        return {'n': 0}
    pnl = [float(r['pnl_pct']) for r in rows]
    years: dict[str, list[float]] = defaultdict(list)
    for row, value in zip(rows, pnl):
        years[row['hold_date'][:4]].append(value)
    yearly = {
        year: {'n': len(values), 'wr': pct(sum(x > 0 for x in values), len(values)),
               'avg_pnl': round(sum(values) / len(values), 4)}
        for year, values in sorted(years.items())
    }
    return {
        'n': len(rows),
        'wr': pct(sum(x > 0 for x in pnl), len(pnl)),
        'avg_pnl': round(sum(pnl) / len(pnl), 4),
        'sl_pct': pct(sum(r['exit_reason'] == 'SL_HIT' for r in rows), len(rows)),
        'yearly': yearly,
        'min_year_n': min(x['n'] for x in yearly.values()),
        'min_year_wr': min(x['wr'] for x in yearly.values()),
    }


def prior_weekday(date: str) -> str:
    current = datetime.strptime(date, '%Y%m%d').date() - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current.strftime('%Y%m%d')


def fetch_exchange(date: str, exchange: str):
    try:
        if exchange == 'SH':
            df = ak.stock_margin_detail_sse(date)
            code_col, bal_col, buy_col = '标的证券代码', '融资余额', '融资买入额'
        else:
            df = ak.stock_margin_detail_szse(date)
            code_col, bal_col, buy_col = '证券代码', '融资余额', '融资买入额'
        if df.empty:
            return None
        rows = {}
        intensities = []
        for _, x in df.iterrows():
            code = str(x[code_col]).zfill(6)
            bal, buy = float(x[bal_col] or 0), float(x[buy_col] or 0)
            intensity = buy / bal if bal > 0 else 0.0
            rows[code] = {'balance': bal, 'buy': buy, 'buy_intensity': intensity}
            intensities.append(intensity)
        intensities.sort()
        return {'rows': rows, 'n': len(rows), 'median_buy_intensity': intensities[len(intensities) // 2]}
    except Exception:
        return None


def fetch_pit_day(hold_date: str):
    """Find the latest exchange date strictly before hold; retry weekdays for holidays."""
    probe = prior_weekday(hold_date)
    for _ in range(10):
        sh, sz = fetch_exchange(probe, 'SH'), fetch_exchange(probe, 'SZ')
        if sh is not None and sz is not None:
            return hold_date, probe, sh, sz
        probe = prior_weekday(probe)
    return hold_date, '', None, None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with SRC.open(newline='') as f:
        source_rows = list(csv.DictReader(f))
    source_rows = [r for r in source_rows if r.get('pnl_pct') not in ('', None)]
    holds = sorted({d8(r['hold_time']) for r in source_rows})
    pit_by_hold, source_failures = {}, []
    # Four workers preserve a modest request rate while cutting the full 788-date
    # source gate from a long serial network wait to a bounded audit operation.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_pit_day, hold) for hold in holds]
        for pos, future in enumerate(as_completed(futures), 1):
            hold, pit_date, sh, sz = future.result()
            if not pit_date:
                source_failures.append(hold)
            else:
                pit_by_hold[hold] = (pit_date, sh, sz)
            if pos % 50 == 0 or pos == len(holds):
                print(f'PIT_SOURCE {pos}/{len(holds)} ready={len(pit_by_hold)}', flush=True)

    output = []
    for r in source_rows:
        hold = d8(r['hold_time'])
        pit = pit_by_hold.get(hold)
        row = {**r, 'hold_date': hold, 'pit_margin_date': '', 'margin_eligible': 'false',
               'margin_buy_intensity': '', 'margin_daily_median_buy_intensity': '',
               'margin_intensity_state': 'SOURCE_UNAVAILABLE'}
        if pit:
            pit_date, sh, sz = pit
            exchange = 'SH' if r['symbol'].endswith('.SH') else 'SZ'
            data = sh if exchange == 'SH' else sz
            row['pit_margin_date'] = pit_date
            record = data['rows'].get(r['symbol'][:6])
            if record:
                row['margin_eligible'] = 'true'
                row['margin_buy_intensity'] = f"{record['buy_intensity']:.12f}"
                row['margin_daily_median_buy_intensity'] = f"{data['median_buy_intensity']:.12f}"
                row['margin_intensity_state'] = (
                    'MARGIN_HIGH_BUY_INTENSITY'
                    if record['buy_intensity'] >= data['median_buy_intensity']
                    else 'MARGIN_LOW_BUY_INTENSITY'
                )
            else:
                row['margin_intensity_state'] = 'NON_MARGIN_ELIGIBLE'
        output.append(row)

    baseline = metrics(output)
    groups = {state: metrics([r for r in output if r['margin_intensity_state'] == state])
              for state in ('MARGIN_HIGH_BUY_INTENSITY', 'MARGIN_LOW_BUY_INTENSITY', 'NON_MARGIN_ELIGIBLE')}
    decisions = {}
    for state, m in groups.items():
        if not m.get('n'):
            decisions[state] = {'passes_discovery': False}
            continue
        yearly = m['yearly']
        decisions[state] = {
            'n>=300': m['n'] >= DISCOVERY_GATE['n_min'],
            'each_year_n>=40': all(x['n'] >= DISCOVERY_GATE['year_n_min'] for x in yearly.values()),
            'wr_uplift>=5pp': m['wr'] - baseline['wr'] >= DISCOVERY_GATE['wr_uplift_pp_min'],
            'avg_pnl_uplift>=1pp': m['avg_pnl'] - baseline['avg_pnl'] >= DISCOVERY_GATE['avg_pnl_uplift_pp_min'],
            'min_year_wr_uplift>=3pp': m['min_year_wr'] - baseline['min_year_wr'] >= DISCOVERY_GATE['min_year_wr_uplift_pp_min'],
        }
        decisions[state]['passes_discovery'] = all(decisions[state].values())

    fields = list(output[0]) if output else []
    with (OUT / 'v395_rows.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(output)
    report = {
        'version': 'V395_PIT_MARGIN_FINANCING_AVAILABILITY_AND_REPLAY_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'fixed V381 trades only; no candidate regeneration, execution change, or fitted thresholds',
        'pit_contract': 'strictly last completed exchange session before intraday hold; no hold-date margin data used',
        'predeclared_states': 'margin eligible and previous-session financing-buy-intensity versus same-day exchange median',
        'source_dates_required': len(holds), 'source_dates_ready': len(pit_by_hold),
        'source_date_coverage_pct': pct(len(pit_by_hold), len(holds)), 'source_failures': source_failures,
        'baseline': baseline, 'states': groups, 'discovery_gate': DISCOVERY_GATE, 'state_decisions': decisions,
        'invariants': {'all_feature_dates_strictly_before_hold': all(r['pit_margin_date'] < r['hold_date'] for r in output if r['pit_margin_date']),
                       'all_source_rows_preserved': len(output) == len(source_rows), 'no_outcome_field_used_to_construct_feature': True},
        'artifacts': {'out_dir': str(OUT), 'rows': str(OUT / 'v395_rows.csv'), 'latest': str(LATEST)},
    }
    report['decision'] = ('MARGIN_INFORMATION_LAYER_READY_FOR_INDEPENDENT_REPLAY'
                          if any(x.get('passes_discovery') for x in decisions.values())
                          else 'NO_MARGIN_INFORMATION_GATE_PASS__BRANCH_CLOSED')
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v395_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
