#!/usr/bin/env python3
"""V540 independent raw-bar Oracle for the frozen V539 seed contract.

This implementation deliberately does not import V539. It re-derives every
identity from the same source-isolated Sina m15 raw bars, compares the full
causal identity tuple to V539's frozen outcome-blind seed file, and never
reads any bar after its calculated entry identity. It never opens outcomes or
writes production, frontend, watchlist, or position state.
"""
from __future__ import annotations

import csv
import gzip
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
V539 = AUDIT / 'v539_sina_m15_ssl_bos_fvg_seed_gate_latest.json'
OUT = AUDIT / f'v540_sina_m15_ssl_bos_fvg_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v540_sina_m15_ssl_bos_fvg_independent_oracle_latest.json'
LEFT = RIGHT = 3
SWEEP_PCT = 0.003
BOS_MAX_BARS = 12
RETEST_MAX_BARS = 20
IDENTITY = ('symbol', 'swing_time', 'sweep_time', 'reference_high_time', 'bos_time', 'fvg_time', 'reclaim_time', 'entry_time')


def positive(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number > 0 and math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def bars(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return []
    out: list[dict[str, Any]] = []
    for row in raw if isinstance(raw, list) else []:
        stamp = str(row.get('t') or '')
        values = [positive(row.get(key)) for key in ('o', 'h', 'l', 'c')]
        if len(stamp) == 14 and all(value is not None for value in values):
            out.append({'t': stamp, 'd': stamp[:8], 'o': values[0], 'h': values[1], 'l': values[2], 'c': values[3]})
    return sorted(out, key=lambda row: row['t'])


def swing_flags(rows: list[dict[str, Any]]) -> tuple[list[bool], list[bool]]:
    low, high = [False] * len(rows), [False] * len(rows)
    for index in range(LEFT, len(rows) - RIGHT):
        window = rows[index - LEFT:index] + rows[index + 1:index + RIGHT + 1]
        low[index] = rows[index]['l'] < min(row['l'] for row in window[:LEFT]) and rows[index]['l'] <= min(row['l'] for row in window[LEFT:])
        high[index] = rows[index]['h'] > max(row['h'] for row in window[:LEFT]) and rows[index]['h'] >= max(row['h'] for row in window[LEFT:])
    return low, high


def derive(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lows, highs = swing_flags(rows)
    known_low: int | None = None
    known_high: int | None = None
    waiting: list[dict[str, Any]] = []
    emitted: list[dict[str, Any]] = []
    last_entry = -1
    for now in range(len(rows)):
        # A 3-right pivot has been known only after right bars and one fully
        # completed subsequent bar; that is the earliest point it may be used.
        eligible = now - RIGHT - 1
        if eligible >= 0 and lows[eligible]:
            known_low, known_high = eligible, None
        if (eligible >= 0 and highs[eligible] and known_low is not None
                and eligible > known_low and rows[eligible]['h'] > rows[known_low]['l']):
            known_high = eligible

        current = rows[now]
        ongoing: list[dict[str, Any]] = []
        for item in waiting:
            if item['stage'] == 'BREAK':
                if now - item['sweep'] > BOS_MAX_BARS:
                    continue
                if current['c'] > item['high_price']:
                    item['stage'] = 'GAP'
                    item['bos'] = now
                ongoing.append(item)
                continue
            if item['stage'] == 'GAP':
                if now - item['bos'] > RETEST_MAX_BARS:
                    continue
                if now >= 2 and rows[now - 2]['h'] < current['l']:
                    item['stage'] = 'TOUCH'
                    item['fvg'] = now
                    item['gap_low'] = rows[now - 2]['h']
                    item['gap_high'] = current['l']
                ongoing.append(item)
                continue
            if now - item['fvg'] > RETEST_MAX_BARS:
                continue
            touched = current['l'] <= item['gap_high'] and current['h'] >= item['gap_low']
            reclaimed = current['c'] >= item['gap_high']
            if now > item['fvg'] and touched and reclaimed:
                entry = now + 1
                if entry < len(rows) and entry > last_entry:
                    emitted.append({
                        'symbol': symbol,
                        'swing_time': rows[item['low']]['t'],
                        'sweep_time': rows[item['sweep']]['t'],
                        'reference_high_time': rows[item['high']]['t'],
                        'bos_time': rows[item['bos']]['t'],
                        'fvg_time': rows[item['fvg']]['t'],
                        'reclaim_time': current['t'],
                        'entry_time': rows[entry]['t'],
                    })
                    last_entry = entry
                continue
            ongoing.append(item)
        waiting = ongoing

        # New sweep state is appended after existing states were evaluated.
        if known_low is not None and known_high is not None:
            pivot, reference = rows[known_low], rows[known_high]
            if current['l'] <= pivot['l'] * (1 - SWEEP_PCT) and current['c'] > pivot['l']:
                waiting.append({'stage': 'BREAK', 'low': known_low, 'high': known_high, 'sweep': now, 'high_price': reference['h']})
    return emitted


def tuple_of(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[key]) for key in IDENTITY)


def frozen_rows() -> tuple[Path, set[tuple[str, ...]]]:
    report = json.loads(V539.read_text())
    path = Path(report['artifacts']['seeds'])
    with path.open(newline='', encoding='utf-8') as handle:
        return path, {tuple_of(row) for row in csv.DictReader(handle)}


def main() -> None:
    frozen_path, expected = frozen_rows()
    OUT.mkdir(parents=True, exist_ok=False)
    generated: list[dict[str, Any]] = []
    short_files: list[str] = []
    for path in sorted(RAW.glob('*_m15.json.gz')):
        rows = bars(path)
        if len(rows) < 100:
            short_files.append(path.name)
            continue
        symbol = path.name.removesuffix('_m15.json.gz').replace('_', '.')
        generated.extend(derive(symbol, rows))
    actual = {tuple_of(row) for row in generated if row['entry_time'][:4] in {'2025', '2026'}}
    missing, extra = expected - actual, actual - expected
    output = OUT / 'v540_oracle_identities.csv'
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=IDENTITY)
        writer.writeheader(); writer.writerows(generated)
    result = {
        'version': 'V540_SINA_M15_SSL_BOS_FVG_INDEPENDENT_ORACLE_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'source_contract': 'Sina source-isolated m15 only; partial 2025-04..2026-07 range; no cross-source bars.',
        'oracle_contract': 'Independent state-machine derivation of frozen V539 chronology; compares only causal event identities, never outcomes.',
        'frozen_seed_source': str(frozen_path),
        'm15_files_scanned': len(list(RAW.glob('*_m15.json.gz'))),
        'excluded_short_files': short_files,
        'expected_identities': len(expected),
        'oracle_identities': len(actual),
        'missing_identities': len(missing),
        'extra_identities': len(extra),
        'identity_match': not missing and not extra,
        'samples': {'missing': [dict(zip(IDENTITY, row)) for row in sorted(missing)[:10]], 'extra': [dict(zip(IDENTITY, row)) for row in sorted(extra)[:10]]},
        'decision': 'V540_ORACLE_PASS__ONE_FROZEN_PARTIAL_RANGE_REPLAY_AUTHORIZED' if not missing and not extra else 'V540_ORACLE_MISMATCH__NO_OUTCOME_REPLAY',
        'artifacts': {'dir': str(OUT), 'oracle_identities': str(output)},
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    (OUT / 'v540_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
