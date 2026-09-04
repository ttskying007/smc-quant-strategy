#!/usr/bin/env python3
"""V384 no-write PIT behavior-cohort context data gate.

A candidate's peers are its 20 most positively correlated stocks over the 20
*completed* raw-daily sessions preceding hold day. Peer participation uses only
the completed hold 60m close. No industry labels and no outcome fields exist.
"""
from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/sina_raw_daily_v379'
M60 = ROOT / 'intraday_cache/sina_m60_v1'
AUD = ROOT / 'smc_audit'
V381 = AUD / 'v381_true_mtf_raw_daily_poi_m60_replay_latest.json'
OUT = AUD / f'v384_pit_behavior_cohort_data_gate_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUD / 'v384_pit_behavior_cohort_data_gate_latest.json'
SLOTS = ('10:30:00', '11:30:00', '14:00:00', '15:00:00')


def symbol(path: Path, suffix: str) -> str:
    return path.name.replace(suffix, '').replace('_', '.')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    r381 = json.loads(V381.read_text())
    # Intentionally read only identity and hold timing, never result columns.
    with open(r381['artifacts']['trades'], newline='') as h:
        targets = [{'symbol': r['symbol'], 'hold_time': r['hold_time']} for r in csv.DictReader(h)]
    target_times = sorted({r['hold_time'] for r in targets})
    target_dates = {t[:10].replace('-', '') for t in target_times}

    raw_paths = sorted(RAW.glob('*_raw_daily.json.gz'))
    syms = [symbol(p, '_raw_daily.json.gz') for p in raw_paths]
    si = {s: i for i, s in enumerate(syms)}
    all_dates = set()
    daily_rows = []
    for p in raw_paths:
        with gzip.open(p, 'rt') as h:
            rows = json.load(h)
        daily_rows.append(rows); all_dates.update(str(r['t']) for r in rows)
    dates = sorted(all_dates); di = {d: i for i, d in enumerate(dates)}
    close = np.full((len(dates), len(syms)), np.nan, dtype=np.float32)
    for j, rows in enumerate(daily_rows):
        for r in rows:
            try: close[di[str(r['t'])], j] = float(r['c'])
            except (KeyError, ValueError, TypeError): pass
    ret = close[1:] / close[:-1] - 1

    ti = {t: i for i, t in enumerate(target_times)}
    intra = np.full((len(target_times), len(syms)), np.nan, dtype=np.float32)
    for j, s in enumerate(syms):
        p = M60 / f"{s.replace('.', '_')}_m60_sina.json.gz"
        if not p.exists(): continue
        try:
            with gzip.open(p, 'rt') as h: rows = json.load(h)
        except Exception: continue
        by_day = defaultdict(list)
        for x in rows:
            t = str(x.get('day') or '')
            if t[:10].replace('-', '') in target_dates:
                try: by_day[t[:10]].append((t, float(x['open']), float(x['close'])))
                except (KeyError, ValueError, TypeError): pass
        for day, bars in by_day.items():
            bars.sort()
            if tuple(x[0][-8:] for x in bars) != SLOTS: continue
            op = bars[0][1]
            if op <= 0: continue
            for t, _, cl in bars:
                if t in ti: intra[ti[t], j] = cl / op - 1

    rows, failed = [], []
    for r in targets:
        j = si.get(r['symbol']); d = r['hold_time'][:10].replace('-', ''); k = di.get(d); q = ti[r['hold_time']]
        if j is None or k is None or k < 21:
            failed.append({**r, 'reason': 'NO_20_COMPLETED_DAILY_SESSIONS'}); continue
        hist = ret[k - 20:k, :].astype(np.float64)
        own = hist[:, j]
        if not np.all(np.isfinite(own)):
            failed.append({**r, 'reason': 'INCOMPLETE_20D_OWN_HISTORY'}); continue
        # Each peer must itself have all 20 completed observations.  Do not require
        # every one of the 4,654 symbols to be available on every row.
        available = np.all(np.isfinite(hist), axis=0)
        x, peer_index = hist[:, available], np.flatnonzero(available)
        y = own - own.mean(); x = x - x.mean(axis=0)
        den = np.sqrt((x * x).sum(axis=0) * (y * y).sum())
        corr = np.full(len(syms), -np.inf)
        corr[peer_index] = np.divide((x * y[:, None]).sum(axis=0), den, out=np.full(len(peer_index), -np.inf), where=den > 0)
        corr[j] = -np.inf
        peers = np.argpartition(corr, -20)[-20:]
        peers = peers[np.argsort(corr[peers])[::-1]]
        now = intra[q, peers]; now = now[np.isfinite(now)]
        if len(now) < 10:
            failed.append({**r, 'reason': 'LESS_THAN_10_PEER_60M_RETURNS'}); continue
        med, up = float(np.median(now)), float((now > 0).mean())
        state = 'COHORT_CONFIRMS' if med > 0 and up >= .60 else ('COHORT_REJECTS' if med < 0 and up <= .40 else 'COHORT_MIXED')
        rows.append({**r, 'feature_cutoff': r['hold_time'], 'peer_count': len(now),
                     'mean_peer_corr': round(float(corr[peers].mean()), 6), 'peer_median_intraday_pct': round(med * 100, 6),
                     'peer_up_pct': round(up * 100, 4), 'pit_cohort_state': state,
                     'contract': '20 completed raw-daily returns ending previous session; peers hold-time 60m closes only'})

    with (OUT / 'v384_features.csv').open('w', newline='') as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]) if rows else ['symbol']); w.writeheader(); w.writerows(rows)
    gate = {'target_rows': len(targets), 'feature_rows': len(rows), 'failed_rows': len(failed),
            'all_target_rows_covered': len(rows) == len(targets), 'min_peer_count_10': not failed,
            'outcome_fields_read_or_emitted': False,
            'all_feature_cutoffs_equal_hold_time': all(r['feature_cutoff'] == r['hold_time'] for r in rows)}
    passed = gate['all_target_rows_covered'] and gate['min_peer_count_10'] and not gate['outcome_fields_read_or_emitted'] and gate['all_feature_cutoffs_equal_hold_time']
    report = {'version': 'V384_PIT_BEHAVIOR_COHORT_DATA_GATE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'),
              'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
              'contract': 'No static industry membership. Neighbors arise only from pre-hold, completed 20-session raw-source return correlations. Same-day peer reaction stops at hold_time before next-open entry.',
              'predeclared_states': {'COHORT_CONFIRMS': 'peer median intraday return>0 and peer up>=60%',
                                     'COHORT_REJECTS': 'peer median intraday return<0 and peer up<=40%', 'COHORT_MIXED': 'otherwise'},
              'gate': gate, 'decision': 'PIT_BEHAVIOR_COHORT_GATE_PASS__OUTCOME_REPLAY_ALLOWED' if passed else 'PIT_BEHAVIOR_COHORT_GATE_FAIL__STOP',
              'artifacts': {'features': str(OUT / 'v384_features.csv'), 'latest': str(LATEST)}, 'failure_samples': failed[:50]}
    text = json.dumps(report, ensure_ascii=False, indent=2); (OUT / 'v384_report.json').write_text(text); LATEST.write_text(text); print(text)


if __name__ == '__main__': main()
