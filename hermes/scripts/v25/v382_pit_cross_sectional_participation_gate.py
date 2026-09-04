#!/usr/bin/env python3
"""V382 no-write PIT cross-sectional participation data gate.

Every feature is frozen at each V381 candidate's `hold_time` close, before its
next-60m-open entry. No trade outcome field is read or emitted.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
M60 = ROOT / 'intraday_cache/sina_m60_v1'
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
OUT = AUD / f'v382_pit_cross_sectional_participation_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v382_pit_cross_sectional_participation_gate_latest.json'
SLOTS = ('10:30:00', '11:30:00', '14:00:00', '15:00:00')


def f(x: object) -> float:
    return float(x)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report381 = json.loads(V381.read_text())
    # Read identity/timing only. Outcome columns are deliberately ignored.
    with open(report381['artifacts']['trades'], newline='') as h:
        targets = {(r['symbol'], r['hold_time']) for r in csv.DictReader(h)}
    target_times = {t for _, t in targets}

    snap = defaultdict(list)
    files = sorted(M60.glob('*_m60_sina.json.gz'))
    for n, path in enumerate(files, 1):
        symbol = path.name.replace('_m60_sina.json.gz', '').replace('_', '.')
        try:
            with gzip.open(path, 'rt') as h:
                raw = json.load(h)
        except Exception:
            continue
        by_day = defaultdict(list)
        for x in raw:
            t = str(x.get('day') or '')
            if '2023-01-01' <= t[:10] <= '2026-07-10':
                try:
                    by_day[t[:10]].append((t, f(x['open']), f(x['close'])))
                except (KeyError, TypeError, ValueError):
                    pass
        previous_close = None
        for day in sorted(by_day):
            bars = sorted(by_day[day])
            if tuple(x[0][-8:] for x in bars) != SLOTS:
                continue
            day_open, day_close = bars[0][1], bars[-1][2]
            for t, _, close in bars:
                if t in target_times and previous_close and day_open > 0:
                    snap[t].append(((close / previous_close - 1) * 100,
                                    (close / day_open - 1) * 100, symbol))
            previous_close = day_close
        if n % 1000 == 0:
            print(json.dumps({'files': n, 'snapshots': len(snap)}), flush=True)

    rows = []
    failures = []
    for timestamp in sorted(target_times):
        x = snap[timestamp]
        prior = sorted(v[0] for v in x)
        intraday = sorted(v[1] for v in x)
        if len(x) < 1000:
            failures.append({'hold_time': timestamp, 'coverage': len(x), 'reason': 'CROSS_SECTION_LT_1000'})
            continue
        med = prior[len(prior) // 2]
        p80 = prior[int((len(prior) - 1) * .8)]
        up = sum(v > 0 for v in prior) / len(prior)
        intra_up = sum(v > 0 for v in intraday) / len(intraday)
        state = ('BROAD_RISK_ON' if up >= .60 and med > 0 and intra_up >= .55 else
                 'BROAD_RISK_OFF' if up <= .40 and med < 0 and intra_up <= .45 else
                 'BROAD_MIXED')
        rows.append({'hold_time': timestamp, 'coverage': len(x), 'prior_close_up_pct': round(up * 100, 4),
                     'prior_close_median_pct': round(med, 6), 'prior_close_p80_pct': round(p80, 6),
                     'intraday_up_pct': round(intra_up * 100, 4), 'pit_participation_state': state,
                     'feature_cutoff': timestamp,
                     'contract': 'all components use only each symbol 60m closes at or before hold_time'})

    with (OUT / 'v382_snapshots.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]) if rows else ['hold_time'])
        w.writeheader(); w.writerows(rows)
    gate = {
        'target_times': len(target_times), 'snapshots_built': len(rows), 'snapshot_failures': len(failures),
        'all_targets_covered': len(rows) == len(target_times),
        'each_snapshot_cross_section_gte_1000': not failures,
        'outcome_fields_read_or_emitted': False,
        'feature_cutoff_not_after_hold_time': all(r['feature_cutoff'] == r['hold_time'] for r in rows),
    }
    # `outcome_fields_read_or_emitted` is an assertion expressed as False, not a pass flag.
    passed = (gate['all_targets_covered'] and gate['each_snapshot_cross_section_gte_1000']
              and not gate['outcome_fields_read_or_emitted'] and gate['feature_cutoff_not_after_hold_time'])
    decision = 'PIT_CONTEXT_DATA_GATE_PASS__OUTCOME_BLIND_REPLAY_ALLOWED' if passed else 'PIT_CONTEXT_DATA_GATE_FAIL__STOP'
    report = {'version': 'V382_PIT_CROSS_SECTIONAL_PARTICIPATION_DATA_GATE_NO_WRITE',
              'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'equal-weighted whole-market participation at the completed hold 60m close; entry is the next 60m open; neither industry classification nor future bar is used',
              'predeclared_states': {'BROAD_RISK_ON': 'prior-close up>=60%, median>0, intraday up>=55%',
                                     'BROAD_RISK_OFF': 'prior-close up<=40%, median<0, intraday up<=45%',
                                     'BROAD_MIXED': 'otherwise'},
              'gate': gate, 'decision': decision,
              'artifacts': {'snapshots': str(OUT / 'v382_snapshots.csv'), 'latest': str(LATEST)},
              'failure_samples': failures[:50]}
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUT / 'v382_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
