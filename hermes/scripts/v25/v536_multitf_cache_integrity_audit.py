#!/usr/bin/env python3
"""No-write integrity audit for already-complete V536 raw multi-timeframe cache.

Verifies each committed symbol only against its own same-source raw daily bars:
15m has 16 standard slots/day, 60m has 4, timestamps are strictly ordered,
and weekly OHLCV is an exact ISO-week aggregation of raw daily. It creates
research audit JSON only; it never writes signals, trades, or production state.
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
CACHE = ROOT / 'intraday_cache/raw_multitf_v536'
AUDIT = ROOT / 'smc_audit'
M60 = {'1030', '1130', '1400', '1500'}
M15 = {'0945', '1000', '1015', '1030', '1045', '1100', '1115', '1130', '1315', '1330', '1345', '1400', '1415', '1430', '1445', '1500'}


def load(path: Path) -> list[dict]:
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        rows = json.load(f)
    if not isinstance(rows, list) or not rows:
        raise ValueError('empty_or_non_list')
    return rows


def slots(rows: list[dict], expected_days: set[str], wanted: set[str]) -> tuple[int, int]:
    per: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        per[row['d']].append(row)
    missing = expected_days - set(per)
    bad = sum(
        len(per[d]) != len(wanted) or {x['t'][8:12] for x in per[d]} != wanted
        for d in expected_days & set(per)
    )
    return len(missing), bad


def audit(symbol: str) -> dict:
    base = symbol.replace('.', '_')
    try:
        daily = load(CACHE / 'daily' / f'{base}_daily.json.gz')
        weekly = load(CACHE / 'weekly' / f'{base}_weekly.json.gz')
        m60 = load(CACHE / 'm60' / f'{base}_m60.json.gz')
        m15 = load(CACHE / 'm15' / f'{base}_m15.json.gz')
        ds = [x['t'] for x in daily]
        valid_daily = all(x['o'] > 0 and x['h'] >= max(x['o'], x['c']) and x['l'] <= min(x['o'], x['c']) for x in daily)
        ordered = all(ds[i] < ds[i + 1] for i in range(len(ds) - 1))
        expected = set(ds)
        m60_missing, m60_bad = slots(m60, expected, M60)
        m15_missing, m15_bad = slots(m15, expected, M15)
        weeks: dict[tuple[int, int], list[dict]] = defaultdict(list)
        for bar in daily:
            d = datetime.strptime(bar['t'], '%Y%m%d')
            weeks[d.isocalendar()[:2]].append(bar)
        aggregate = []
        for bars in weeks.values():
            aggregate.append((bars[-1]['t'], bars[0]['o'], max(x['h'] for x in bars), min(x['l'] for x in bars), bars[-1]['c'], sum(x['v'] for x in bars)))
        actual = [(x['t'], x['o'], x['h'], x['l'], x['c'], x['v']) for x in weekly]
        weekly_exact = aggregate == actual
        ok = valid_daily and ordered and not m60_missing and not m60_bad and not m15_missing and not m15_bad and weekly_exact
        return {'symbol': symbol, 'ok': ok, 'daily_bars': len(daily), 'weekly_bars': len(weekly), 'm60_bars': len(m60), 'm15_bars': len(m15), 'm60_missing_days': m60_missing, 'm60_bad_slot_days': m60_bad, 'm15_missing_days': m15_missing, 'm15_bad_slot_days': m15_bad, 'weekly_exact': weekly_exact}
    except Exception as exc:
        return {'symbol': symbol, 'ok': False, 'error': repr(exc)}


def main() -> None:
    symbols = sorted(p.name.replace('_daily.json.gz', '').replace('_', '.') for p in (CACHE / 'daily').glob('*_daily.json.gz'))
    rows = [audit(s) for s in symbols]
    failed = [r for r in rows if not r['ok']]
    report = {'version': 'V536_RAW_MULTITF_CACHE_INTEGRITY_AUDIT', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'research_only': True, 'production_write': False, 'symbols': len(rows), 'passed': len(rows) - len(failed), 'failed': len(failed), 'decision': 'CURRENT_CACHE_INTEGRITY_PASS' if not failed else 'CURRENT_CACHE_INTEGRITY_FAIL', 'failure_samples': failed[:50]}
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = AUDIT / f'v536_multitf_cache_integrity_{stamp}.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (AUDIT / 'v536_multitf_cache_integrity_latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
